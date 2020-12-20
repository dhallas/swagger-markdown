
"""
Swagger pre-processor
"""

from markdown import util
from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension
import json
import re


def labelValue(out, content, label):
    value = content.get(label) or ''
    if value:
        out.append(f'<span class="sw-label">{label}:</span> <span class="sw-value">{value}</span>')

def pathRepr(path, required):
    out = []
    for p in path[1:]:
        if p in required:
            out.append(f'<strong>{p}</strong>')
        else:
            out.append(p)
        
    return '.'.join(out).replace('.[0]', '[0]')

def idRepr(path):
    return '.'.join(path)


class SwaggerDefinition():

    def __init__(self, file=None, definitionsUrl='', definitionNames=[]):
        self.defaultFile = file
        self.definitionsUrl = definitionsUrl
        self.definitionName = None
        self.definitionNames = definitionNames

        self.defaultDetailsField = ['description', 'example', 'maximum', 'minimum',
            'minItems', 'maxItems', 'uniqueItems', 'exclusiveMinimum', 'minLength',
            'maxLength', 'multipleOf', 'readOnly', 'writeOnly', 'minProperties', 
            'maxProperties', 'enum', 'pattern']

        self.excludeField = ['type', 'items', 'properties', 'required', '$ref', 'xml', 'format', 'name']

    # Typical input
    # :swg-def: swagger.json AccessibilityProperties
    # :swg-def: AccessibilityProperties
    # :swg-path: /my-project"
    def handleLine(self, line):
        content = line.split(' ')
        file = content[1]
        if not file.endswith('.json'):
          file = self.defaultFile

        self.definitionName = content[-1]

        with open(file) as json_file:
            data = json.load(json_file)
            defs = data['definitions']
            definition = defs[self.definitionName]
            return self.definitionTable(definition, self.definitionName)

    def table(self, body, id):
        return f"""<table class="sw-table" id="/definitions/{id}">
        <thead><tr><th>Name</th><th>Type</th><th>Details</th></tr></thead>
        <tbody>{body}</tbody>
        </table>
        """

    def definitionTable(self, definition, defname):
        body = []
        required = definition.get('required', [])
        properties = definition.get('properties', {})
        for name, content in properties.items():
            self.addTableLine([defname], body, name, content, required)
        return self.table(body=''.join(body), id=defname)

    def makeDetails(self, content):
        out = []
        keys = content.keys()
        for detail in keys:
            if detail not in self.excludeField:
                labelValue(out, content, detail)

        return '<br>'.join(out)

    def typeAndFormat(self, content):
        t = content.get('type')
        if t:
            f = content.get('format')
            if f:
                return f'{t} {f}'
            return t

    def refLink(self, ref):
        bits = ref.split('/')
        name = bits[len(bits) - 1]
        url = f'{self.definitionsUrl}{ref}'
        # if the current name is included in the current page, we can ignore definitionsUrl
        if name in self.definitionNames:
            url = ref

        return f'<a href="{url}">{name}</a>' 

    def addTableLine(self, path, body, name, content, required=[]):
        ctype = self.typeAndFormat(content)
        details = self.makeDetails(content)
        ctypeOut = ctype

        # could create issue if the name clash...
        # TODO: smarter path
        required = required + content.get('required', [])

        items = content.get('items')

        if ctype == 'array':
            if items.get('$ref'):
                ctypeOut = f'array of {self.refLink(items.get("$ref"))}'
            elif items.get('type'):
                ctypeOut = f'array of {self.typeAndFormat(items)}'
            else:
                ctypeOut = 'array of object'

        newPath = path + [name]
        body.append(f'''<tr id="{idRepr(newPath)}">
          <td>{pathRepr(newPath, required)}</td>
          <td>{ctypeOut}</td>
          <td>{details}</td>
        </tr>''')

        if ctype == 'object':
            for n, c in content['properties'].items():
                self.addTableLine(newPath, body, n, c, required)

        if ctype == 'array' and items and not items.get('$ref') and items.get("type") == 'object':
            self.addTableLine(newPath, body, '[0]', content.get('items'), required)


class SwaggerPath():

    def __init__(self, file=None):
        self.defaultFile = file
        self.defaultDetailsField = ['description', 'example', 'maximum', 'minimum',
            'minItems', 'maxItems', 'uniqueItems', 'exclusiveMinimum', 'minLength',
            'maxLength', 'multipleOf', 'readOnly', 'writeOnly', 'minProperties', 
            'maxProperties', 'in' , 'enum', 'pattern']

        self.excludeField = ['type', 'items', 'properties', 'required', '$ref', 'xml', 'schema', 'format', 'name']

    # Typical input
    # :swg-path: /my-project"
    # :swg-path: test_swagger.json /users/{userId}
    def handleLine(self, line):
        content = line.split(' ')
        file = content[1]
        if not file.endswith('.json'):
          file = self.defaultFile

        self.path = content[-1]

        with open(file) as json_file:
            data = json.load(json_file)
            pathDef = data['paths'][self.path]
            return self.pathRepr(pathDef)

    def pathRepr(self, pathDef):
        out = []
        verbs = pathDef.keys()
        for verb in verbs:
            out.append(f'''<p class="sw-path">
                <span class="sw-verb">{verb.upper()}</span>
                <span class="sw-path-url">{self.path}</span></p>''')
            verbDef = pathDef[verb]
            summary = verbDef.get('summary')
            out.append(f'''<p class="sw-summary">{summary}</p>''')
            parameters = verbDef.get('parameters')
            out.append(self.parameters(parameters))

            responses = verbDef.get('responses')
            out.append(self.responses(responses))

        return '\n'.join(out)

    def responses(self, responses):
        return ''

    def parametersTable(self, body):
        return f"""<table class="sw-table" id="/paths/{self.path}/parameters">
        <caption>Parameters</caption>
        <thead><tr><th>Name</th><th>Type</th><th>Details</th></tr></thead>
        <tbody>{body}</tbody>
        </table>
        """

    def makeContentType(self, parameter):
        schema = parameter.get('schema')
        # seems wrong acording to the spec, but it seems
        # some decide to shove type and format without schema
        # https://swagger.io/docs/specification/describing-parameters/
        if not schema:
            schema = parameter
        t = schema.get('type')
        if t:
            f = schema.get('format')
            if f:
                return f'{t} {f}'
            return t
        ref = schema.get('$ref')
        if ref:
            url = f'{ref}'
            bits = ref.split('/')
            name = bits[len(bits) - 1]
            return f'<a href="{url}">{name}</a>'

    def makeDetails(self, content):
        out = []
        keys = content.keys()
        for detail in keys:
            if detail not in self.excludeField:
                labelValue(out, content, detail)

        return '<br>'.join(out)

    def outNames(self, names=[]):
        out = []
        for n in names:
            out.append(f'<strong>{n["name"]}</strong>' if n.get("required") else n["name"])
        return '.'.join(out).replace('.[0]', '[0]')

    def line(self, p, names):
        out = []
        name = p.get('name') or ''

        if name:
            names.append({ "name": name, "required": p.get('required') })

        outName = self.outNames(names)
        out.append(f'''<tr>
            <td>{outName}</td>
            <td>{self.makeContentType(p)}</td>
            <td>{self.makeDetails(p)}</td>
        </tr>''')

        ctype = p.get('type') or p.get('schema', {}).get('type')
        items = p.get('items')

        if ctype == 'object':
            props = p.get('properties') or p.get('schema') and p.get('schema').get('properties')
            for key, value in props.items():
                out.append(self.line(value, names + [{'name': key}]))

        if ctype == 'array' and items and not items.get('$ref'):
            out.append(self.line(items, names=names + [{'name': '[0]'}]))

        return ''.join(out)

    def parameters(self, parameters):
        out = []
        for p in parameters:
            out.append(self.line(p, []))
    
        return self.parametersTable(''.join(out))

class SwaggerPreprocessor(Preprocessor):
    """Swagger include Preprocessor"""

    def __init__(self, md, file=None, definitionsUrl=''):
        self.defaultFile = file
        self.definitionsUrl = definitionsUrl
        self.definitionNames = []
        super(SwaggerPreprocessor, self).__init__(md)

    def run(self, lines):
        out = []
        for line in lines:
            if line.startswith(':swg-def: '):
              handler = SwaggerDefinition(
                file=self.defaultFile, 
                definitionsUrl=self.definitionsUrl,
                definitionNames=self.definitionNames
              )
              out = out + handler.handleLine(line).split("\n")
              self.definitionNames.append(handler.definitionName)
            elif line.startswith(':swg-path: '):
              handler = SwaggerPath(file=self.defaultFile)
              out = out + handler.handleLine(line).split("\n")
            else:
              out.append(line)

        return out


class SwaggerExtension(Extension):
    """Swagger Extension"""

    def __init__(self, **kwargs):
      self.config = {
          'file' : ['swagger.json', 'The default path of the swagger file'],
          'definitionsUrlRoot' : ['', 'An URL added in front of each definition'],
      }
      super(SwaggerExtension, self).__init__(**kwargs)

    def extendMarkdown(self, md, md_globals):
        file = self.getConfig('file')
        definitionsUrl = self.getConfig('definitionsUrlRoot')
        md.preprocessors.add('swaggerinclude', 
          SwaggerPreprocessor(md, file=file, definitionsUrl=definitionsUrl), '_begin')


def makeExtension(*args, **kwargs):
    """Return extension."""

    return SwaggerExtension(*args, **kwargs)