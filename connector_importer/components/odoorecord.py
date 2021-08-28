# Author: Simone Orsi
# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.addons.component.core import Component


class OdooRecordHandler(Component):
    """Interact w/ odoo importable records."""

    _name = "importer.odoorecord.handler"
    _inherit = "importer.base.component"
    _usage = "odoorecord.handler"

    unique_key = ""
    unique_key_is_xmlid = False
    importer = None
    # By default odoo ignores create_uid/write_uid in vals.
    # If you enable this flags and `create_uid` and/or `write_uid`
    # are found in values they gonna be used for sudo.
    # Same for `create_date`.
    override_create_uid = False
    override_create_date = False
    override_write_uid = False
    override_write_date = False

    def _init_handler(self, importer=None, unique_key=None, unique_key_is_xmlid=False):
        try:
            options = self.work.options["record_handler"]
        except AttributeError:
            options = {}
        self.importer = importer or options.get("importer")
        self.unique_key = unique_key or options.get("unique_key", "")
        self.unique_key_is_xmlid = unique_key_is_xmlid
        self.override_create_uid = options.get("override_create_uid", False)
        self.override_create_date = options.get("override_create_date", False)
        self.override_write_uid = options.get("override_write_uid", False)
        self.override_write_date = options.get("override_write_date", False)

    def odoo_find_domain(self, values, orig_values):
        """Domain to find the record in odoo."""
        return [(self.unique_key, "=", values[self.unique_key])]

    def odoo_find(self, values, orig_values):
        """Find any existing item in odoo."""
        if self.unique_key == "":
            # if unique_key is None we might use as special find domain
            return self.model
        if self.unique_key_is_xmlid:
            item = self.env.ref(values[self.unique_key], raise_if_not_found=False)
            return item
        item = self.model.search(
            self.odoo_find_domain(values, orig_values),
            order="create_date desc",
            limit=1,
        )
        return item

    def odoo_exists(self, values, orig_values):
        """Return true if the items exists."""
        return bool(self.odoo_find(values, orig_values))

    def update_translations(self, odoo_record, translatable, ctx=None):
        """Write translations on given record."""
        ctx = ctx or {}
        context = self.env.context.copy()
        context.update(ctx)
        for lang, values in translatable.items():
            self._update_field_translations(odoo_record, lang, values, context)
            # TODO: confirm this has no effect to IrTranslation
            # odoo_record.with_context(lang=lang, **self.write_context()).write(
            #     values.copy()
            # )

    def _update_field_translations(self, odoo_record, lang, values, ctx=None):
        IrTranslation = self.env["ir.translation"]
        lang_values = [
            {
                "type": "model",
                "name": fname,
                "lang": lang,
                "res_id": odoo_record.id,
                "src": getattr(odoo_record, fname, ""),
                "value": value,
                "state": "translated",
                }
            for fname, value in values.items()]
        IrTranslation.with_context(ctx)._upsert_translations(lang_values)

    def odoo_pre_create(self, values, orig_values):
        """Do some extra stuff before creating a missing record."""

    def odoo_post_create(self, odoo_record, values, orig_values):
        """Do some extra stuff after creating a missing record."""

    def create_context(self):
        """Inject context variables on create."""
        return dict(
            self.importer._odoo_create_context(),
            # mark each action w/ this flag
            connector_importer_session=True,
        )

    def odoo_create(self, values, orig_values):
        """Create a new odoo record."""
        self.odoo_pre_create(values, orig_values)
        # copy values to not affect original values (mainly for introspection)
        values_for_create = values.copy()
        # purge unneeded values
        self._odoo_write_purge_values(None, values_for_create)
        odoo_record = self.model.with_context(**self.create_context()).create(
            values_for_create
        )
        # force uid
        if self.override_create_uid and values.get("create_uid"):
            self._force_value(odoo_record, values, "create_uid")
        # force create date
        if self.override_create_date and values.get("create_date"):
            self._force_value(odoo_record, values, "create_date")
        self.odoo_post_create(odoo_record, values, orig_values)
        translatable = self.importer.collect_translatable(values, orig_values)
        self.update_translations(odoo_record, translatable)
        # Set the external ID if necessary
        if self.unique_key_is_xmlid:
            external_id = values[self.unique_key]
            if not self.env.ref(external_id, raise_if_not_found=False):
                module, id_ = external_id.split(".", 1)
                self.env["ir.model.data"].create(
                    {
                        "name": id_,
                        "module": module,
                        "model": odoo_record._name,
                        "res_id": odoo_record.id,
                        "noupdate": False,
                    }
                )
        return odoo_record

    def odoo_pre_write(self, odoo_record, values, orig_values):
        """Do some extra stuff before updating an existing object."""

    def odoo_post_write(self, odoo_record, values, orig_values):
        """Do some extra stuff after updating an existing object."""

    def write_context(self):
        """Inject context variables on write."""
        return dict(
            self.importer._odoo_write_context(),
            # mark each action w/ this flag
            connector_importer_session=True,
        )

    def odoo_write(self, values, orig_values):
        """Update an existing odoo record."""
        # pass context here to be applied always on retrieved record
        odoo_record = self.odoo_find(values, orig_values).with_context(
            **self.write_context()
        )
        # copy values to not affect original values (mainly for introspection)
        values_for_write = values.copy()
        # purge unneeded values
        self._odoo_write_purge_values(odoo_record, values_for_write)
        # hook before write
        self.odoo_pre_write(odoo_record, values_for_write, orig_values)
        # do write now
        odoo_record.write(values_for_write)
        # force uid
        if self.override_write_uid and values.get("write_uid"):
            self._force_value(odoo_record, values, "write_uid")
        # force write date
        if self.override_write_date and values.get("write_date"):
            self._force_value(odoo_record, values, "write_date")
        # hook after write
        self.odoo_post_write(odoo_record, values_for_write, orig_values)
        # handle translations
        translatable = self.importer.collect_translatable(values, orig_values)
        self.update_translations(odoo_record, translatable)
        return odoo_record

    def _force_value(self, record, values, fname):
        # the query construction is not vulnerable to SQL injection, as we are
        # replacing the table and column names here.
        # pylint: disable=sql-injection
        query = "UPDATE {} SET {} = %s WHERE id = %s".format(record._table, fname)
        self.env.cr.execute(query, (values[fname], record.id))
        record.invalidate_cache([fname])

    def _odoo_write_purge_values(self, odoo_record, values):
        # remove non fields values
        field_names = tuple(values.keys())
        for fname in field_names:
            if fname not in self.model._fields:
                values.pop(fname)
        if not odoo_record:
            return
        # remove fields having the same value
        field_names = tuple(values.keys())
        if self.work.options.record_handler.skip_fields_unchanged:
            current_values = odoo_record.read(field_names, load="_classic_write")
            for k, v in current_values[0].items():
                if values.get(k) == v:
                    values.pop(k)
