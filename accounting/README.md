# Accounting

The `accounting` app tracks the **points** and **study credits** each lab holds. It includes a ledger, where every change to a balance is recorded as a row in `LedgerEntry`, and those rows are never edited or deleted. The ledger entries are associated with 'lots' (batches of points/credits), since these may have different terms (e.g. costs, expiration dates) and/or scopes (e.g. points that can only be used for a specific study).

- A **lot** (`Lot`) is one batch of points or credits given to a lab. This might be a points top-up, a membership allowance, or a single study purchase. When a new lot is created, it will add at least one ledger row: granted lots first appear in the ledger with a GRANT row, and deficit lots first appear in the ledger with a CONSUME row.
- A **ledger entry** (`LedgerEntry`) is one movement against a lot. A lot's balance is the sum of its entries.

The lots and ledger entries are associated with only one of these units:

- **Study credits** always belong to the lab.
- **Points** are either *unassigned* (held by the lab) or belong to one study. A study can only ever spend its own points.

## 1. Set up

This assumes you already have a working local lookit-api instance.

1. Check that your branch includes the `accounting` app.

   It should be in the top-level directory and listed in `INSTALLED_APPS` in `project/settings.py`.

2. Create the accounting tables in your local DB:

   ```bash
   make migrate
   ```

3. Add some fake data:

   ```bash
   make seedledger
   ```

   This seeds the first lab that has at least one study, other than the Sandbox lab and Demo lab, with some lots of points/credits and some ledger entries. Pass `--lab <id>` to pick a different lab (including the Sandbox/Demo labs: 1 or 2). This command adds the following to the lab:
   - 1,000 unassigned points
   - 200 points for one of the lab's studies
   - 500 unassigned points dated 30 days in the future
   - 4 net study credits
     - grants 2 credits
     - spends 3 credits (which creates a deficit lot of 1)
     - grants 5 credits (this grant automatically settles the deficit of 1, leaving 4 in the last grant lot)

   It ends by printing the balances. Running this command again adds another set to the same lab.

4. Check that the ledger is consistent:

   ```bash
   make checkledger
   ```

   It either prints `Ledger OK` or lists each problem it found, and exits non-zero if there are any. It only reads data, so it is safe to run multiple times, including on production.

## 2. Reset the lots and ledger

Ledger rows cannot be edited or deleted by the admin, by the Django ORM, or by SQL. The database enforces this. So to remove/modify data, you have to reset everything:

```bash
make resetledger
```

Because this command is destructive, it will first show you how many lots and ledger entries it will delete, and from which database and host, and then ask you to type the database name (e.g. `lookit` locally) to confirm the deletion. In scripts you can use `--confirm <database name>` to skip the prompt. This command is for local/staging only: it refuses to run when `ENVIRONMENT=production`.

To rebuild the tables themselves, for example after changing the migrations, you don't want to just reset the data. Instead, you need to roll the migrations back to 0 and migrate again:

```bash
docker compose run --rm web uv run ./manage.py migrate accounting zero
```

```bash
make migrate
```

The ledger data also blocks deleting the labs, studies, and responses it refers to. If you want to delete one of those locally and find that the deletion is blocked, just reset the ledger first (`make resetledger`).

## 3. Viewing and adding points and credits

**Lab detail page** 

When logged in as an admin, open a lab's page at `/exp/labs/<id>/`. Below the license and usage section, you'll see the *Study credits* and *Points* tables which show the lab's balances of the following:

- Study credits
- Unassigned points
- Study-specific points (listed separately for each study)
- Total points

The totals include grants dated in the future.

**Admin pages**

- **Add points or credits** at *Accounting → Lots → Add* (`/__CTRL__/accounting/lot/add/`).
  - Choose the lab, the unit (points or study credits), the grant type, and the amount.
  - For a *study allowance* (points for a specific study), choose the study.
  - Saving creates the lot and adds its opening ledger entry. (If the lab has a deficit in the same unit and scope, saving will also pay it off, which means the available points/credits will be less than the value added.)
- **Edit a lot.** After a lot is created, only the expiry date, consumption priority, and notes can be changed. Everything else is fixed once the lot exists, and lots cannot be deleted.
- **Correct a mistake.** Nothing is edited in place. Instead, each correction is a new record with the associated reason.
  - *To add points or credits* that were missing due to a mistake, add a new lot with grant type *Adjustment* and put the reason in its notes.
  - [TO BE IMPLEMENTED] *A lot given to the wrong lab*: use *Correct this lot* to remove the unspent points from the wrong lab’s lot, then add a new lot for the right lab with the same grant type, amount, and expiry as the original, and note the original lot’s id in its notes.
  - [TO BE IMPLEMENTED] *To remove points or credits* due to a mistake, a *Correct this lot* action on the lot's page will write a negative adjustment against that lot, with a required reason. It can't take a lot below zero, so points already spent can't be taken back from that lot.
- [TO BE IMPLEMENTED] **Referral bonuses**
- **Browse ledger entries** at *Accounting → Ledger entries*. This view is read-only. You can filter by unit, entry type, or lab, or search by lab, study, response, or memo.

**Django shell** 

You can also use `accounting/services.py` directly in a shell for things that aren't currently available through the admin pages:

```python
from accounting import services
from accounting.models import GrantType, Unit
from studies.models import Lab

lab = Lab.objects.get(pk=1)
# grant points to a lab
services.grant(lab, 100, Unit.POINT, GrantType.TOP_UP)
# get a lab's point balance
services.lab_balance(lab, Unit.POINT)
# list all of a lab's point lots and their balances, along with grant type and study ID values
list(services.lot_balances(lab, Unit.POINT).values("grant_type", "study_id", "balance"))
```

Every balance function requires a unit. Only create lots and ledger entries through the public functions in `services.py` (currently just `services.grant()`). Never use `Lot.objects.create(...)`, `LedgerEntry.objects.create(...)` or `.save()` on a new object, and don’t call the private methods in `services.py` - those actions will skip the balance updates, deficit settlement, and validation that keep the lots and ledger consistent. The database doesn’t block them, and `make checkledger` won’t always catch the damage. For local test data, use `make seedledger` and `make resetledger` (see sections 1 and 2).

## 4. Switching back to a branch without the accounting app

To go back to branches that pre-date the accounting release:

**No migrations need rolling back.** The accounting tables are new, and no other app's tables or migrations depend on them. On a branch without the app, Django ignores both the tables and accounting's rows in `django_migrations`. Your other data, the site and `make test` all work as normal. Tests use a separate database built from that branch's own migrations.

**One catch: deleting labs, studies, responses, or users.** The accounting tables refer to these, and the database refuses to delete anything that ledger data still points to. You can't end up with ledger rows pointing at records that no longer exist; instead, the delete fails with an `IntegrityError`. If you'll be deleting any of those, just reset the ledger **before** switching branches:

```bash
make resetledger
```

Or to remove the accounting tables completely, migrate the app back to zero **before** switching branches.

```bash
docker compose run --rm web uv run ./manage.py migrate accounting zero
```

When you switch back, the tables and data are where you left them. If you rolled the app back, you'll need to run `make migrate` again.
