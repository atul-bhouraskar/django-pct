import django.template.base
import django.template.defaulttags
import django.template.loader
import django.template.loader_tags

import pickle


class PeregrineCompilerException(Exception):
    pass


class CompiledOutput(object):
    def __init__(self, template_name):
        self.name = get_class_name_from_template_name(template_name)
        self.base_name = 'PreCompiledTemplate'
        self.imports = {'pickle'}
        self.object_creators = {}
        self.block_render_list = []

    def set_parent_template(self, parent_template_name):
        self.base_name = get_class_name_from_template_name(
            parent_template_name)

    def set_block_nodes(self, block_nodes):
        for block_node in block_nodes:
            render_list = []
            for node in block_node.nodelist:
                node.pct__serialise__(0, self, render_list)
            self.block_render_list.append((block_node.name, render_list))
        #print self.imports, self.object_creators

    def register_object(self, obj):
        module_name = type(obj).__module__
        class_name = type(obj).__name__
        self.imports.add('%s' % module_name)
        creator = ObjectCreator(module_name, class_name)
        self.object_creators['%s.%s' % (module_name, class_name)] = creator
        return creator.render_constructor_template()

    def render(self):
        output_list = []
        for imp in self.imports:
            output_list.append('import %s' % imp)

        for name, creator in self.object_creators.items():
            output_list.append(creator.render())

        for name, render_list in self.block_render_list:
            output_list.append("""
    def render_block_%s(self, render_list):
        render_list.extend(
            [%s]
        )
            """ % (name, ','.join(render_list)))

        with open(self.name + '.py', 'w') as f:
            f.write('\n'.join(output_list))


class ObjectCreator(object):
    def __init__(self, module_name, class_name):
        self.module_name = module_name
        self.class_name = class_name

    def render_constructor_template(self):
        return 'PCT_OBJ_%s(%%s)' % self.class_name

    def render(self):
        return """
class PCT_OBJ_%s(%s.%s):
    def __init__(self, *args, **kwargs):
        for attr, value in kwargs.items():
            setattr(self, attr, value)
        """ % (self.class_name, self.module_name, self.class_name)

    def __repr__(self):
        return self.render()


SERIALISE_METHOD = 'pct__serialise__'


def do_nodelist_serialise(self, level, output, render_list):
    for node in self:
        if hasattr(node, SERIALISE_METHOD):
            getattr(node, SERIALISE_METHOD)(level+1, output, render_list)


def do_node_serialise(self, level, output, render_list):
    obj_template = output.register_object(self)
    node_dict = self.__dict__
    print '\t'*level, 'Node - ', type(self)
    kwargs_list = []
    for name, val in node_dict.items():
        if hasattr(val, SERIALISE_METHOD):
            value = getattr(val, SERIALISE_METHOD)(level+1, output, render_list)
        else:
            try:
                value = 'pickle.loads("""' + pickle.dumps(val) + '""")'
            except TypeError:
                value = '"UNKNOWN_%s"' % (val,)
        kwargs_list.append('%s=%s' % (name, value))
    render_list.append(obj_template % ",".join(kwargs_list))



def do_text_node_serialise(self, level, output, render_list):
    output.register_object(self)
    render_list.append(u'u"""%s"""' % self.s)


def do_if_serialise(self, level, output, render_list):
    obj_template = output.register_object(self)
    kwargs_list = []
    for condition, nodelist in self.conditions_nodelists:
        kwargs_list.append('condition="%s, %s"' % (type(condition), type(nodelist)))
    render_list.append(obj_template % ",".join(kwargs_list))


def null_serialise(self, level, output, render_list):
    output.register_object(self)


setattr(django.template.base.NodeList, SERIALISE_METHOD, do_nodelist_serialise)
setattr(django.template.base.Node, SERIALISE_METHOD, do_node_serialise)
setattr(django.template.loader.LoaderOrigin, SERIALISE_METHOD, null_serialise)
setattr(django.template.base.TextNode, SERIALISE_METHOD, do_text_node_serialise)
setattr(django.template.defaulttags.IfNode, SERIALISE_METHOD, do_if_serialise)


def precompile(template_name):
    output = CompiledOutput(template_name)
    # get the compiled template
    t = django.template.loader.get_template(template_name)
    nodelist = t.nodelist
    extends_nodes = nodelist.get_nodes_by_type(
        django.template.loader_tags.ExtendsNode)
    if extends_nodes:
        node = extends_nodes[0]
        parent = node.parent_name.var
        if isinstance(parent, django.template.base.Variable):
            # not implemented yet
            raise PeregrineCompilerException(
                'Pre-compilation of variable base templates not implemented')
        output.set_parent_template(parent)
        block_nodes = node.get_nodes_by_type(
            django.template.loader_tags.BlockNode)
    else:
        block_nodes = nodelist.get_nodes_by_type(
            django.template.loader_tags.BlockNode)

    output.set_block_nodes(block_nodes)

    if not extends_nodes:
        # this is a base template
        pass
    output.render()
    #render_types(nodelist)
    return nodelist


def get_class_name_from_template_name(template_name):
    return 'PCT_' + template_name.replace('/', '__').replace('.', '___')


def render_types(nodelist, level=0):
    for node in nodelist:
        print '\t'*level, type(node)  #, repr(node)
        if hasattr(node, 'nodelist'):
            render_types(node.nodelist, level+1)