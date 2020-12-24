
"""
Swagger pre-processor
"""

from markdown import util
from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension
import yaml
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
        self.excludeField = ['type', 'items', 'properties', 'required', '$ref', 'xml', 'format', 'name']

    def getDefinitionName(self, line):
        content = line.split(' ')
        return content[-1]

    # Typical input
    # :swg-def: swagger.json AccessibilityProperties
    # :swg-def: AccessibilityProperties
    # :swg-path: /my-project"
    def handleLine(self, line):
        content = line.split(' ')
        file = content[1]
        if not file.endswith('.json'):
          file = self.defaultFile

        self.definitionName = self.getDefinitionName(line)

        with open(file) as json_file:
            data = json.load(json_file)
            defs = data['definitions']
            definition = defs[self.definitionName]
            return self.definitionTable(definition, self.definitionName)

    def table(self, body, id):
        # some markdown theme disable all style if a class is present
        return f"""<table data-type="sw-table" id="/definitions/{id}"> 
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

    def details(self, content):
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
        ref = content.get('$ref')
        if ref:
            return self.refLink(ref)

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
        details = self.details(content)
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

    def __init__(self, file=None, definitionsUrl='', definitionNames=[], config={}):
        self.defaultFile = file
        self.definitionsUrl = definitionsUrl
        self.definitionNames = definitionNames

        self.excludeField = ['type', 'items', 'properties', 'required', '$ref', 'xml', 'schema', 'format', 'name']

        sectionConfig = config.get("sections", {})
    
        self.config = {
            "responseExamples": sectionConfig.get("responseExamples", True),
            "responseTables": sectionConfig.get("responseTables", True),
            "parameters": sectionConfig.get("parameters", True),
            "verbs": config.get("verbs", "all")
        }

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
            self.data = json.load(json_file)
            pathDef = self.data['paths'][self.path]
            return self.pathRepr(pathDef)

    def pathRepr(self, pathDef):
        out = []
        verbs = pathDef.keys()
        for verb in verbs:
            if self.config['verbs'] != 'all' and not verb in self.config['verbs']:
                continue

            out.append(f'''<p class="sw-path">
                <span class="sw-verb">{verb.upper()}</span>
                <span class="sw-path-url">{self.path}</span></p>''')
            verbDef = pathDef[verb]
            summary = verbDef.get('summary')
            out.append(f'''<p class="sw-summary">{summary}</p>''')
            parameters = verbDef.get('parameters')

            if self.config['parameters']:
                out.append(self.parameters(parameters))

            if self.config['responseTables']:
                out.append(self.responses(verbDef))

            if self.config['responseExamples']:
                out.append(self.responsesExamples(verbDef))

        return '\n'.join(out)

    def responses(self, verbDef):
        responses = verbDef.get('responses')
        produces = verbDef.get('produces') or []
        producesStr = ', '.join(produces)
        if producesStr:
            producesStr = f'({producesStr})'
        out = []
        for name, content in responses.items():
            out.append(self.response(name, content))
        body = ''.join(out)
        return f"""<table data-type="sw-table" id="/paths{self.path}/responses">
        <caption>Responses {producesStr}</caption>
        <thead><tr><th>Code</th><th>Description</th><th>Body</th></tr></thead>
        <tbody>{body}</tbody>
        </table>
        """

    def responsesExamples(self, verbDef):
        responses = verbDef.get('responses')
        out = []
        for name, content in responses.items():
            schema = content.get('schema')
            if not schema:
                continue
            obj = self.responseMap(schema)
            out.append(f'''
Response example {name}

```json
{json.dumps(obj, indent=2)}
```
''')
        return '\n'.join(out)


    def response(self, name, response):
        description = response.get('description')
        schema = self.contentType(response) or ''
        return f'''<tr>
            <td>{name}</td>
            <td>{description}</td>
            <td>{schema}</td>
        </tr>'''

    def parametersTable(self, body):
        return f"""<table data-type="sw-table" id="/paths{self.path}/parameters">
        <caption>Parameters</caption>
        <thead><tr><th>Name</th><th>Type</th><th>Details</th></tr></thead>
        <tbody>{body}</tbody>
        </table>
        """

    def contentType(self, obj):
        # obj is a Paramteter or a Response
        schema = obj.get('schema')
        # seems wrong acording to the spec, but it seems
        # some decide to shove type and format without schema
        # https://swagger.io/docs/specification/describing-parameters/
        if not schema:
            schema = obj
        t = schema.get('type')
        if t:
            f = schema.get('format')
            if f:
                return f'{t} {f}'
            return t
        ref = schema.get('$ref')
        if ref:
            return self.refLink(ref)

    def refLink(self, ref):
        bits = ref.split('/')
        name = bits[len(bits) - 1]
        url = f'{self.definitionsUrl}{ref}'
        # if the current name is included in the current page, we can ignore definitionsUrl
        if name in self.definitionNames:
            url = ref

        return f'<a href="{url}">{name}</a>' 

    def details(self, content):
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

    def parameter(self, p, names):
        """
        Handles one parameter
        """
        out = []
        name = p.get('name') or ''

        if name:
            names.append({ "name": name, "required": p.get('required') })

        outName = self.outNames(names)
        out.append(f'''<tr>
            <td>{outName}</td>
            <td>{self.contentType(p)}</td>
            <td>{self.details(p)}</td>
        </tr>''')

        ctype = p.get('type') or p.get('schema', {}).get('type')
        items = p.get('items')

        if ctype == 'object':
            props = p.get('properties') or p.get('schema') and p.get('schema').get('properties')
            for key, value in props.items():
                out.append(self.parameter(value, names + [{'name': key}]))

        if ctype == 'array' and items and not items.get('$ref'):
            out.append(self.parameter(items, names=names + [{'name': '[0]'}]))

        return ''.join(out)

    def parameters(self, parameters):
        out = []
        for p in parameters:
            out.append(self.parameter(p, []))
    
        return self.parametersTable(''.join(out))

    def getRandomValue(self, content):
        ctype = content.get('type')
        format = content.get('format')
        example = content.get('example')
        if example:
            return example
        enum = content.get('enum')
        if enum:
            return enum[0]

        if ctype == 'integer' or ctype == 'number':
            return 123
        elif ctype == 'string':
            if format == 'date':
                return '2019-07-21'
            if format == 'date-time':
                return '2017-07-21T17:32:28Z'
            if format == 'password':
                return '*****'
            return 'lorem ipsum'
        elif ctype == 'boolean':
            return True
        
        return ctype

    def responseMap(self, content):
        name = content.get('name')

        ctype = content.get('type')
        ref = content.get('$ref')

        if ctype == 'array':
            items = content.get('items')
            return [self.responseMap(items)]

        elif ctype == 'object':
            properties = content.get('properties', {})
            c = {}
            for name, content in properties.items():
                c[name] = self.responseMap(content)
            return c
        elif ref:
            defName = ref.split('#/definitions/')[1]
            if defName in self.data['definitions']:
                return self.responseMap(
                    self.data['definitions'][defName])
        else:
            return self.getRandomValue(content)
class SwaggerPreprocessor(Preprocessor):
    """Swagger include Preprocessor"""

    def __init__(self, md, file=None, definitionsUrl=''):
        self.defaultFile = file
        self.definitionsUrl = definitionsUrl
        super(SwaggerPreprocessor, self).__init__(md)

    def getConfig(self, index, lines):
        yamlOut = []
        while index < len(lines):
            line = lines[index]
            if line.startswith('    '):
                yamlOut.append(line[4:])
                del lines[index]
            else:
                break
        if len(yamlOut):
            return yaml.load('\n'.join(yamlOut), Loader=yaml.FullLoader)
        return {}

    def run(self, lines):
        out = []

        # a list of all definition present in this document
        definitionNames = []
        for line in lines:
            if line.startswith(':swg-def: '):
                definitionNames.append(SwaggerDefinition().getDefinitionName(line))

        for index, line in enumerate(lines):
            if line.startswith(':swg-def: '):
                handler = SwaggerDefinition(
                    file=self.defaultFile, 
                    definitionsUrl=self.definitionsUrl,
                    definitionNames=definitionNames
                )
                out = out + handler.handleLine(line).split("\n")
            elif line.startswith(':swg-path: '):
                lineConfig = self.getConfig(index + 1, lines)
                handler = SwaggerPath(
                    file=self.defaultFile,
                    definitionsUrl=self.definitionsUrl,
                    definitionNames=definitionNames,
                    config=lineConfig
                )
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
