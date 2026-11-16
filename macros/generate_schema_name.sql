{% macro generate_schema_name(custom_schema_name, node) -%}
    {# Use the folder-declared schema as-is (silver / gold) instead of prefixing
       it with the profile's default schema. #}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
