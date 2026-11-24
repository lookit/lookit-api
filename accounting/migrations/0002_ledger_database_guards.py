"""Database-level guards for the ledger that Django cannot express.

1. A ledger entry's unit and lab must be the same unit/lab associated with the ledger entry's lot.
   A CHECK constraint cannot look at another table, so this is a composite foreign key
   from (lot_id, lab_id, unit) to Lot(id, lab_id, unit). It is not deferrable, so
   a mismatched row is rejected at INSERT, and it also stops a lot's lab or unit being
   changed once it has rows.

2. The ledger is append-only. The model guards in LedgerEntry.save() and
   .delete() do not cover QuerySet.update(), QuerySet.delete() or raw SQL, so a trigger
   rejects UPDATE and DELETE outright. The one exception is the UPDATE Django issues
   itself when a user referenced by created_by is deleted (on_delete=SET_NULL): clearing
   created_by and changing nothing else is allowed, so deleting a staff account does not
   fail. TRUNCATE is deliberately not blocked; it is not a row operation and the test
   runner uses it to flush the database.
"""

from django.db import migrations

FORWARD_SQL = """
ALTER TABLE accounting_ledgerentry
    ADD CONSTRAINT accounting_ledgerentry_lot_lab_unit_fk
    FOREIGN KEY (lot_id, lab_id, unit)
    REFERENCES accounting_lot (id, lab_id, unit)
    ON UPDATE NO ACTION ON DELETE NO ACTION
    NOT DEFERRABLE;

CREATE FUNCTION accounting_ledgerentry_immutable() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.created_by_id IS NOT NULL
       AND NEW.created_by_id IS NULL
       AND (to_jsonb(NEW) - 'created_by_id') = (to_jsonb(OLD) - 'created_by_id') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'accounting_ledgerentry is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation',
              HINT = 'Write a correcting entry instead.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER accounting_ledgerentry_immutable
    BEFORE UPDATE OR DELETE ON accounting_ledgerentry
    FOR EACH ROW EXECUTE FUNCTION accounting_ledgerentry_immutable();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS accounting_ledgerentry_immutable ON accounting_ledgerentry;
DROP FUNCTION IF EXISTS accounting_ledgerentry_immutable();
ALTER TABLE accounting_ledgerentry
    DROP CONSTRAINT IF EXISTS accounting_ledgerentry_lot_lab_unit_fk;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
