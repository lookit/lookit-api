"""Queries and managers.

The trick is in constructs like this:

F(field_name) + F(field_name).bitand(reduce(operator.or_, bitmasks, 0))

which might produce a SQL query like so:

WHERE ... "accounts_child"."existing_conditions" <
        (("accounts_child"."existing_conditions" + (1 * ("accounts_child"."existing_conditions" & 12))))

This is a "bit hack" that relies on the fact that a bit state ANDed with a mask will give us a result that is
greater than zero if ~any~ of the bits match between the mask and the state. So what we are saying is, "give me
rows from this table where my_field is less than my_field + (my_field AND some_mask). This will only ever be true if
there are matching set bits between my_field and some_mask.

For has_one_of, we take all the bits we care about and OR them into a single mask (e.g., 01101)

For has_all_of, we split the individual bits we care about (e.g. 01000, 00100, 00001 - only powers of 2 in decimal)
and split them across AND filters in the where clause of our SQL query.
"""

import operator
from functools import reduce

from django.db import models
from django.db.models import F, Q


class BitfieldQuerySet(models.QuerySet):
    def has_one_of(self, field_name: str, bitmasks: list):
        """Check to see that field_name has at least one of the bits in bitmasks.

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
            A filtered queryset
        """

        def make_query_dict(specific_mask):
            return {
                f"{field_name}__lt": F(field_name) + F(field_name).bitand(specific_mask)
            }

        has_each = map(lambda c: Q(**make_query_dict(c)), bitmasks)

        filter_query = reduce(operator.and_, has_each, Q(**{f"{field_name}__gt": 0}))

        return self.filter(filter_query)
