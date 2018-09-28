from typing import List, Tuple, Type

from jinja2 import Template

from . import INDENT, ModelsStructureType, OBJECTS_DELIMITER, indent, sort_fields
from ..dynamic_typing import AbsoluteModelRef, ImportPathList, MetaData, ModelMeta, compile_imports, metadata_to_typing


def template(pattern: str, indent: str = INDENT) -> Template:
    """
    Remove indent from triple-quotes string and return jinja2.Template instance
    """
    if "\n" in pattern:
        n = len(indent)
        lines = pattern.split("\n")
        for i in (0, -1):
            if not lines[i].strip():
                del lines[i]

        pattern = "\n".join(line[n:] if line[:n] == indent else line
                            for line in lines)
    return Template(pattern)


class GenericModelCodeGenerator:
    """
    Core of model code generator. Extend it to customize fields of model or add some decorators.
    Note that this class has nothing to do with models structure. It only can add nested models as strings.
    """
    BODY = template("""
    {%- for decorator in decorators -%}
    @{{ decorator }}
    {% endfor -%}
    class {{ name }}:
    
    {%- for code in nested %}
    {{ code }}
    {% endfor -%}
    
    {%- for field in fields %}
        {{ field }}
    {%- endfor %}
    """)

    FIELD: Template = template("{{name}}: {{type}}{% if body %} = {{ body }}{% endif %}")

    def __init__(self, model: ModelMeta, **kwargs):
        self.model = model

    def generate(self, nested_classes: List[str] = None) -> Tuple[ImportPathList, str]:
        """
        :param nested_classes: list of strings that contains classes code
        :return: list of import data, class code
        """
        imports, fields = self.fields
        data = {
            "decorators": self.decorators,
            "name": self.model.name,
            "fields": fields
        }
        if nested_classes:
            data["nested"] = [indent(s) for s in nested_classes]
        return imports, self.BODY.render(**data)

    @property
    def decorators(self) -> List[str]:
        """
        :return: List of decorators code (without @)
        """
        return []

    def field_data(self, name: str, meta: MetaData, optional: bool) -> Tuple[ImportPathList, dict]:
        """
        Form field data for template

        :param name: Field name
        :param meta: Field metadata
        :param optional: Is field optional
        :return: imports, field data
        """
        imports, typing = metadata_to_typing(meta)
        data = {
            "name": name,
            "type": typing
        }
        return imports, data

    @property
    def fields(self) -> Tuple[ImportPathList, List[str]]:
        """
        Generate fields strings

        :return: imports, list of fields as string
        """
        required, optional = sort_fields(self.model)
        imports: ImportPathList = []
        strings: List[str] = []
        for is_optional, fields in enumerate((required, optional)):
            for field in fields:
                field_imports, data = self.field_data(field, self.model.type[field], bool(is_optional))
                imports.extend(field_imports)
                strings.append(self.FIELD.render(**data))
        return imports, strings


def _generate_code(
        structure: List[dict],
        class_generator: Type[GenericModelCodeGenerator],
        class_generator_kwargs: dict,
        lvl=0
) -> Tuple[ImportPathList, List[str]]:
    """
    Walk thought models structure and covert them into code

    :param structure: Result of compose_models or similar function
    :param class_generator: GenericModelCodeGenerator subclass
    :param class_generator_kwargs: kwags for GenericModelCodeGenerator init
    :param lvl: Recursion depth
    :return: imports, list of first lvl classes
    """
    imports = []
    classes = []
    for data in structure:
        nested_imports, nested_classes = _generate_code(
            data["nested"],
            class_generator,
            class_generator_kwargs,
            lvl=lvl + 1
        )
        imports.extend(nested_imports)
        gen = class_generator(data["model"], **class_generator_kwargs)
        cls_imports, cls_string = gen.generate(nested_classes)
        imports.extend(cls_imports)
        classes.append(cls_string)
    return imports, classes


def generate_code(structure: ModelsStructureType, class_generator: Type[GenericModelCodeGenerator],
                  class_generator_kwargs: dict = None, objects_delimiter: str = OBJECTS_DELIMITER) -> str:
    """
    Generate ready-to-use code

    :param structure: Result of compose_models or similar function
    :param class_generator: GenericModelCodeGenerator subclass
    :param class_generator_kwargs: kwags for GenericModelCodeGenerator init
    :param objects_delimiter: Delimiter between root level classes
    :return: Generated code
    """
    root, mapping = structure
    with AbsoluteModelRef.inject(mapping):
        imports, classes = _generate_code(root, class_generator, class_generator_kwargs or {})
    if imports:
        imports_str = compile_imports(imports) + objects_delimiter
    else:
        imports_str = ""
    return imports_str + objects_delimiter.join(classes) + "\n"
