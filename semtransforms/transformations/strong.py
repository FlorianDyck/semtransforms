import copy
from copy import deepcopy

from pycparser.c_ast import *

from semtransforms.transformation import *
from semtransforms.util import *

from semtransforms.context import is_generated_identifier
from semtransforms.util import verifier


@find_statements(length=1, modifiable_length=False)
def add_if1(self, parents: List[Node], stmts: Nodes, context: ContextVisitor):
    def transform():
        stmts.replace(If(Constant('int', '1'), stmts[0], None))

    if not isinstance(stmts[0], Decl):
        return transform


@find_expressions()
def re_ref(self, parents: List[Node], expr: Content, context: ContextVisitor):
    if isinstance(expr[0], ID) and not\
            (isinstance(parents[-1], c_ast.StructRef) and parents[-1].field is expr[0]):
        return lambda: expr.replace(UnaryOp("*", UnaryOp("&", expr.content()[0])))


@find_expressions(context=True)
def re_ref_no_methods(self, parents: List[Node], expr: Content, context: ContextVisitor):
    if isinstance(expr[0], ID) and not\
            (isinstance(parents[-1], c_ast.StructRef) and parents[-1].field is expr[0])\
            and not (isinstance(parents[-1], c_ast.FuncCall) and parents[-1].name is expr[0])\
            and not any(isinstance(t, FuncDecl) for t in context.type(expr[0])):
        return lambda: expr.replace(UnaryOp("*", UnaryOp("&", expr.content()[0])))


@find_expressions(context=True)
def re_ref_locals(self, parents: List[Node], expr: Content, context: ContextVisitor):
    if isinstance(expr[0], ID) and expr[0].name not in context.globals and edit_allowed(expr[0].name):
        return lambda: expr.replace(UnaryOp("*", UnaryOp("&", expr.content()[0])))


@find_statements(length=1, modifiable_length=False, context=True)
@verifier.nondet("int")
def add_if_rand(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    if not isinstance(stmts[0], Decl) and duplicateable(stmts[0]):
        return lambda: stmts.replace(If(verifier.nondet_call("int"), stmts[0], deepcopy(stmts[0])))


@find_statements(length=1, modifiable_length=False, context=True)
@verifier.nondet("int")
def deepen_while(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    match stmts[0]:
        case While(cond=cond, stmt=stmt) as w if not (finder.has_side_effects(cond) or finder.has_break(stmt)):
            if finder.has_func_calls(cond): _restructure_loop_with_func_call_condition(context, stmts)

            return lambda: setattr(w, "stmt", While(BinaryOp("&", verifier.nondet_call("int"), deepcopy(cond)), stmt))


@find_statements(length=1, modifiable_length=False)
def to_array(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    def transform():
        decl: Decl = stmts[0]
        for d, p in references(parents[-1], decl):
            d.replace(ArrayRef(name=d.content()[0], subscript=Constant(type="int", value="0")))
        decl.type = ArrayDecl(decl.type, Constant(type="int", value="1"), [])
        if decl.init:
            decl.init = InitList([decl.init])

    if stmts[0].__class__ is Decl:
        return transform


@find_statements(length=0, context=True)
@verifier.error
def if0error(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    return lambda: stmts.replace(If(Constant("int", "0"), verifier.error_call(), None))



@find_statements(length=1, modifiable_length=False, context=True)
def to_method(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    if isinstance(stmts[0], Compound) and not\
            (finder.has_break(stmts[0]) or finder.has_jumps(stmts[0]) or finder.has_return(stmts[0])):

        # Handling struct ref does not seem to be really supported
        # TODO: Fix and drop this condition
        if finder.has_struct_ref(stmts[0]): return
        
        if len(stmts[0].block_items) == 0: return

        name = context.free_name(prefix = "func_")
        # get names and types of all variables defined before used in this block
        urs = unknown_references(stmts[0])
        local_urs = [ur for ur in urs if ur[0][0].name not in context.globals]
        local_names = {ur[0][0].name for ur in local_urs}
        original_params = [context.value(id) for id in local_names]

        # Why is this needed? We can process variable array sizes via pointers
        if any(has_variable_array_size(p) for p in original_params):
            return

        def transform():
            # create pointer params from variables and clear declaration specifiers
            params = [copy.deepcopy(p) for p in original_params]
            for param in params:
                param.init = None
                
                #if isinstance(param.type, ArrayDecl):
                #    param.type = PtrDecl([], param.type.type)

                param.type = PtrDecl([], param.type)
                param.storage = []
                param.funcspec = []

            for node, _ in local_urs:
                node.replace(UnaryOp("*", node[0]))
            # create function at the start of the program
            void_function = _declare_void_function(name, params)
            void_function = _define_function(name, void_function, stmts[0])
            parent_pos    = _find_parent_pos_in_ext(parents)
            parents[0].ext.insert(parent_pos, void_function)
            # call the function
            stmts.replace(FuncCall(ID(name), ExprList([UnaryOp("&", ID(id)) for id in local_names])))

        return transform


@find_statements(length=1, modifiable_length=False, context=True)
def to_recursive(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    if isinstance(stmts[0], While) and not (finder.has_jumps(stmts[0]) or finder.has_return(stmts[0])):

        # Handling struct ref does not seem to be really supported
        # TODO: Fix and drop this condition
        if finder.has_struct_ref(stmts[0]): return

        name = context.free_name(prefix = "func_")

        # get names and types of all variables defined before used in this block
        urs = unknown_references(stmts[0])
        local_urs = [ur for ur in urs if ur[0][0].name not in context.globals]
        local_names = {ur[0][0].name for ur in local_urs}
        original_params = [context.value(id) for id in local_names]

        # Why is this needed? We can process variable array sizes via pointers
        if any(has_variable_array_size(p) for p in original_params):
            return

        def transform():
            # create pointer params from variables and clear declaration specifiers
            params = [copy.deepcopy(p) for p in original_params]
            for param in params:
                param.init = None

                #if isinstance(param.type, ArrayDecl):
                #    param.type = PtrDecl([], param.type.type)

                param.type = PtrDecl([], param.type)
                param.storage = []
                param.funcspec = []

            for node, _ in local_urs:
                node.replace(UnaryOp("*", node[0]))

            def break2return(node: Node):
                for slot in node.__slots__:
                    child = getattr(node, slot)
                    if isinstance(child, list):
                        for i in range(len(child)):
                            if child[i].__class__ in (For, While, Switch):
                                break
                            elif isinstance(child[i], Break):
                                child[i:i+1] = [Return(None)]
                            elif isinstance(child[i], Node):
                                break2return(child[i])
                    elif child.__class__ in (For, While, Switch):
                        break
                    elif isinstance(child, Break):
                        setattr(node, slot, Return(None))
                    elif isinstance(child, Node):
                        break2return(child)
            break2return(stmts[0])

            # create function at the start of the program
            call = FuncCall(ID(name), ExprList([ID(id) for id in local_names]))
            void_function = _declare_void_function(name, params)
            void_function = _define_function(name, void_function, Compound([If(stmts[0].cond, Compound([stmts[0].stmt, call]), None)]))
            parent_pos    = _find_parent_pos_in_ext(parents)
            parents[0].ext.insert(parent_pos, void_function)
            # call the function
            stmts.replace(FuncCall(ID(name), ExprList([UnaryOp("&", ID(id)) for id in local_names])))

        return transform


@find_statements(length=1, modifiable_length=False, context=True)
def insert_method(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    match stmts[0]:
        case FuncCall(name=ID(name=name)) as call if edit_allowed(name) and name in context.func_defs:
            if is_generated_identifier(name, prefix = "func_"):
                # We do not want to reinline an encapsuled function
                return

            func_def = context.func_defs[name]

            if isinstance(func_def, c_ast.Decl):
                # External functions are not inlined
                return

            if finder.has_jumps(func_def.body) or finder.has_return(func_def.body):
                return
            params = func_def.decl.type.args
            params = params.params if params else []
            if any(not can_rename(p.type) for p in params):
                return

            # create free names for temporary storage of params
            param_names = {p.name for p in params}
            temp_names = []
            while len(temp_names) < len(params):
                temp_names.append(context.free_name(prefix = "param_"))

            def transform():
                if params:
                    result = Compound([])
                    # temporary store params with the temporary names
                    for expr, name, param in zip(call.args.exprs, temp_names, params):
                        decl = deepcopy(param)
                        rename(decl, name)
                        decl.init = expr
                        result.block_items.append(decl)

                    inner = Compound([])
                    # store the values in params with the right name
                    result.block_items.append(inner)
                    for name, param in zip(temp_names, params):
                        decl = deepcopy(param)
                        decl.init = ID(name)
                        inner.block_items.append(decl)
                    inner.block_items.append(deepcopy(func_def.body))
                    stmts.replace(result)
                else:
                    stmts.replace(deepcopy(func_def.body))

            return transform


# Helper ----------------------------------------------------------------

def _declare_void_function(name, params):
    return FuncDecl(
        args = ParamList(params),
        type = TypeDecl(
            declname = name,
            quals = [],
            align = None,
            type  = IdentifierType(['void']),
            attrs = None
        ),
        attrs = None
    )


def _define_function(name, declaration, body):
    return FuncDef(
        Decl(
            name = name,
            quals = [],
            align = [],
            storage = [],
            funcspec = [],
            attrs = [],
            type = declaration,
            init = None,
            bitsize = None,
        ),
        None,
        body
    )


def _find_parent_pos_in_ext(parents):
    root = parents[0]
    def_or_others = parents[1]

    if isinstance(def_or_others, FuncDef):
        return next(i for i, child in enumerate(root.ext) if child == def_or_others)
    
    return 0


def _find_nodes(root, node_type):
    
    for attr_name, child in root.children():
        if isinstance(child, node_type):
            yield SingleNode(root, attr_name)
        
        for _other in _find_nodes(child, node_type):
            yield _other



def _restructure_loop_with_func_call_condition(context, loop):

    loop_node  = loop[0]
    loop_cond  = loop_node.cond 
    func_calls = list(_find_nodes(loop_cond, c_ast.FuncCall))
    if len(func_calls) == 0: return

    # Add compound to loop if necessary
    if not isinstance(loop_node.stmt, c_ast.Compound):
        loop_node.stmt = c_ast.Compound(block_items=[loop_node.stmt])

    output_stmts = []
    for func_call in func_calls:
        name = func_call.name.name
        func_def = context.func_defs[name]
        if hasattr(func_def, "decl"): func_def = func_def.decl

        func_type   = func_def.type

        new_name    = context.free_name(prefix = "call_")
        return_type = func_type.type.type

        output_stmts.append(simple_declaration(new_name, return_type, func_call[0]))
        loop_node.stmt.block_items.append(assignment_expression(new_name, func_call[0]))
        func_call.replace(c_ast.ID(name = new_name))
        #print(func_call[0])

    output_stmts.append(loop_node)

    # Replace all
    loop.replace(c_ast.Compound(block_items=output_stmts))

