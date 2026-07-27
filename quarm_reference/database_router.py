from .database import get_database_alias


class QuarmDatabaseRouter:
    """Route Quarm reads correctly and reject ORM write attempts."""

    app_label = "quarm_reference"

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return get_database_alias()
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            raise RuntimeError(
                "The Quarm reference database is read-only. "
                "Use its SELECT-only database account."
            )
        return None

    def allow_relation(self, obj1, obj2, **hints):
        label1 = obj1._meta.app_label
        label2 = obj2._meta.app_label

        if label1 == self.app_label and label2 == self.app_label:
            return True
        if self.app_label in {label1, label2}:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Never create/alter imported tables in the Quarm database.
        if db == get_database_alias():
            return False
        # The app contains only mappings of existing imported tables.
        if app_label == self.app_label:
            return False
        return None
