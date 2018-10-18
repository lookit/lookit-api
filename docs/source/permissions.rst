Permissions
===========

Generic best practices
----------------------

-  Groups are an important abstraction between users and permissions.

   -  If you assign permissions directly to a user it will be difficult
      to find out who has the permissions and difficult to remove them.

-  Creating a Group just to wrap an individual permission is fine.
-  Include the model name when defining model specific permissions.
   Permissions are referenced with app_name and permission codename.
-  Always check for individual permissions. **NEVER CHECK IF SOMEONE
   BELONGS TO A GROUP or ``is_superuser``**
-  ``is_superuser`` implicitly grants all permissions to a user. Any
   permissions check will return ``True`` if a user ``is_superuser``.

Guardian, how does it work?
---------------------------

Django provides model-level permissions. That means that you can allow
users in the Scientist group the ability to read the Report model or
users in the Admin group the ability to create, read, update, and delete
the Report model.

`Guardian <https://django-guardian.readthedocs.io/en/stable/>`__
provides object-level permissions. That means that you can allow users
in the Southern Scientists group the ability to read the a specific
Report instance about Alabama.

Guardian does this by leveraging Django’s generic foreign key field.
This means that Guardian can have a severe performance impact on queries
where you check object-level permissions. It will cause a double join
through Django’s ContentType table. If this becomes non-performant you
can switch to using `direct foreign
keys <https://django-guardian.readthedocs.io/en/stable/userguide/performance.html#direct-foreign-keys>`__.
