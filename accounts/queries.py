"""Constructs for different kinds of queries and managers."""

import ast
import operator
from datetime import date
from functools import reduce
from itertools import chain

from django.db import models
from django.db.models import F, Q
from lark import Lark, Transformer, v_args

from studies.fields import CONDITIONS, LANGUAGES


CONST_MAPPING = {"true": True, "false": False, "null": None}

GENDER_MAPPING = {"male": "m", "female": "f", "other": "o"}

CONDITION_FIELDS = {condition_tuple[0] for condition_tuple in CONDITIONS}

LANGUAGE_FIELDS = {f"speaks_{language_tuple[0]}" for language_tuple in LANGUAGES}

QUERY_GRAMMAR = """
?start: bool_expr

?bool_expr: bool_term ("OR" bool_term)*
?bool_term: bool_factor ("AND" bool_factor)*
?bool_factor: not_bool_factor
              | "(" bool_expr ")"
              | relation_expr
?relation_expr: gender_comparison 
    | gestational_age_comparison 
    | age_in_days_comparison 
    | language_comparison
    | condition_comparison
    | language_count_comparison

not_bool_factor: "NOT" bool_factor

gender_comparison: "gender" (EQ | NE) gender_target

// 24 to 40 weeks
gestational_age_comparison: "gestational_age_in_weeks" comparator GESTATIONAL_AGE_AS_WEEKS

age_in_days_comparison: "age_in_days" comparator INT

language_count_comparison: ("n_languages" | "num_languages") comparator INT

comparator: EQ | NE | LT | LTE | GT | GTE

gender_target: MALE | FEMALE | OTHER_GENDER | UNSPECIFIED_GENDER

language_comparison: LANGUAGE_TARGET

condition_comparison: CONDITION_TARGET

// TERMINALS

LANGUAGE_TARGET: {language_targets}
CONDITION_TARGET: {condition_targets}

GESTATIONAL_AGE_AS_WEEKS: /(2[4-9]|3[0-9]|40)/

EQ: "="
NE: "!="
LT: "<"
LTE: "<="
GT: ">"
GTE: ">="

TRUE: "true"i
FALSE: "false"i
NULL: "null"i

MALE: "male"i | "m"i
FEMALE: "female"i | "f"i
OTHER_GENDER: "other"i | "o"i
UNSPECIFIED_GENDER: "na"i

%import common.INT
%import common.WS
%ignore WS
""".format(
    language_targets=" | ".join([f'"{target}"' for target in LANGUAGE_FIELDS]),
    condition_targets=" | ".join([f'"{target}"' for target in CONDITION_FIELDS]),
)

QUERY_DSL_PARSER = Lark(QUERY_GRAMMAR, parser="earley")


def get_child_eligibility_for_study(child_obj, study_obj):
    return get_child_eligibility(child_obj, study_obj.criteria_expression)


def get_child_eligibility(child_obj, criteria_expr):
    if criteria_expr:
        compiled_tester_func = compile_expression(criteria_expr)

        expanded_child = _get_expanded_child(child_obj)

        return bool(compiled_tester_func(expanded_child))
    else:
        return True


def compile_expression(boolean_algebra_expression: str):
    """Compiles a boolean algebra expression into a python function.

    Args:
        boolean_algebra_expression: a string boolean algebra expression.

    Returns:
        A function.

    Raises:
        lark.exceptions.ParseError: in case we cannot parse the boolean algebra.
    """
    if boolean_algebra_expression:
        parse_tree = QUERY_DSL_PARSER.parse(boolean_algebra_expression)
        func_body = FunctionTransformer().transform(parse_tree)
    else:
        func_body = "True"

    func_text = " ".join(["def property_tester(child_obj):  return", func_body])

    code_object = ast.parse(func_text, mode="exec")

    new_func = compile(code_object, filename="temp.py", mode="exec")

    temp_namespace = {}

    exec(new_func, temp_namespace)

    return temp_namespace["property_tester"]


def _get_expanded_child(child_object):
    """Expands a child object such that it can be evaluated easily.

    The output of this method should be such that _compile_expression
    can evaluate it; i.e. all keys are first-level.

    Args:
        child_object: a accounts.models.Child instance.

    Returns:
        A dict representing the child.
    """
    expanded_child = _to_dict(child_object)

    # 1) Change birthday to age in days.
    age_delta = date.today() - expanded_child.pop("birthday")
    expanded_child["age_in_days"] = age_delta.days

    # 2) Expand existing conditions in-place.
    expanded_conditions = dict(expanded_child.pop("existing_conditions").items())
    expanded_child.update(expanded_conditions)

    # 3) Expand languages in place.
    expanded_languages = {
        f"speaks_{langcode}": boolean
        for langcode, boolean in expanded_child.pop("languages_spoken").items()
    }
    expanded_child.update(expanded_languages)

    ga_enum = expanded_child.pop("gestational_age_at_birth")

    gestational_age_in_weeks = _gestational_age_enum_value_to_weeks(ga_enum)

    expanded_child["gestational_age_in_weeks"] = gestational_age_in_weeks

    return expanded_child


def _to_dict(model_instance):
    """Better version of django.forms.models.model_to_dict.

    Args:
        model_instance: A django model instance.

    Returns:
        A dictionary formed from a model instance.
    """
    opts = model_instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(model_instance)
    return data


def _gestational_age_enum_value_to_weeks(enum_value: int):
    """Convert enum value on child object to actual # of weeks.

    This enables us to directly query the expanded child object with a
    scalar value. 0 == "under 24 weeks"; 17 = "Over 40 weeks". To see
    enumerated values, please reference studies/fields.py.
    """
    return min(max(23, enum_value + 23), 40) if enum_value else None


@v_args(inline=True)
class FunctionTransformer(Transformer):
    def bool_expr(self, bool_term, *others):
        or_clauses = " ".join(f"or {other}" for other in others)
        return f"({bool_term} {or_clauses})"

    def bool_term(self, bool_factor, *others):
        and_clauses = " ".join(f"and {other}" for other in others)
        return f"({bool_factor} {and_clauses})"

    def gender_comparison(self, comparator, target_gender):
        return f"child_obj.get('gender') {'==' if comparator == '=' else comparator} {target_gender}"

    def gestational_age_comparison(self, comparator, num_weeks):
        return f"child_obj.get('gestational_age_in_weeks') {comparator} {num_weeks}"

    def age_in_days_comparison(self, comparator, num_days):
        return f"child_obj.get('age_in_days') {comparator} {num_days}"

    def language_comparison(self, lang_target):
        return f"child_obj.get('{lang_target}', False)"

    def condition_comparison(self, condition_target):
        return f"child_obj.get('{condition_target}', False)"

    def language_count_comparison(self, comparator, num_langs):
        return (
            f"len({{k: v for k, v in child_obj.items() if k.startswith('speaks_') and v}}) "
            f"{comparator} {num_langs}"
        )

    def gender_target(self, gender):
        gender = gender.lower()
        return f"'{GENDER_MAPPING.get(gender, gender)}'"

    def comparator(self, relation):
        return "==" if relation == "=" else relation

    def not_bool_factor(self, bool_factor):
        return f"not {bool_factor}"


class BitfieldQuerySet(models.QuerySet):
    """A QuerySet that can handle bitwise queries intelligently.

    The trick is in constructs like this:  F(field_name) +
    F(field_name).bitand(reduce(operator.or_, bitmasks, 0))  which might
    produce a SQL query like so:

        WHERE ...
        "accounts_child"."existing_conditions" <
        (("accounts_child"."existing_conditions" + (1 * ("accounts_child"."existing_conditions" & 12))))

    This is a "bit hack" that relies on the fact that a bit state ANDed with a mask will give us a result that
    is greater than zero if ~any~ of the bits match between the mask and the state. So what we are saying is,
    "give me rows from this table where my_field is less than my_field + (my_field AND some_mask). This will only
    ever be true if there are matching set bits between my_field and some_mask.

    For has_one_of, we take all the bits we care about and OR them into a single mask (e.g., 01101)

    For has_all_of, we split the individual bits we care about (e.g. 01000, 00100, 00001 - only powers of 2 in decimal)
    and split them across AND filters in the where clause of our SQL query.
    """

    def has_one_of(self, field_name: str, bitmasks: list):
        """Check to see that field_name has at least one of the bits in
        bitmasks.

        Args:
            field_name: The field which we will be querying against - usually a BigInt
            bitmasks: the list of integers which will serve as bitmasks

        Returns:
            A filtered queryset.
        """
        filter_dict = {
            f"{field_name}__gt": 0,
            # field value contains one of supplied field bits
            f"{field_name}__lt": F(field_name)
            + F(field_name).bitand(reduce(operator.or_, bitmasks, 0)),
        }

        return self.filter(**filter_dict)

    def has_all_of(self, field_name: str, bitmasks: list):
        """Check to see that field_name has all of the bits in bitmasks.

        Args:
            field_name: The field which we will be querying against - usually a BigInt
            bitmasks: the list of integers which will serve as bitmasks

        Returns:
            A filtered queryset.
        """

        def make_query_dict(specific_mask):
            return {
                f"{field_name}__lt": F(field_name) + F(field_name).bitand(specific_mask)
            }

        has_each = map(lambda c: Q(**make_query_dict(c)), bitmasks)

        filter_query = reduce(operator.and_, has_each, Q(**{f"{field_name}__gt": 0}))

        return self.filter(filter_query)
