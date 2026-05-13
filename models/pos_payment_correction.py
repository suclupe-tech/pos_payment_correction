from odoo import models, fields, api
from odoo.exceptions import UserError


class PosPaymentCorrection(models.Model):
    _name = "pos.payment.correction"
    _description = "Correccion de Metodo de Pago POS"

    pos_order_id = fields.Many2one(
        "pos.order",
        string="Orden POS",
        required=True,
    )

    pos_config_id = fields.Many2one(
        "pos.config",
        string="Punto de Venta",
        related="pos_order_id.config_id",
        store=True,
    )

    usuario_solicitante_id = fields.Many2one(
        "res.users",
        string="Solicitado por",
        default=lambda self: self.env.user,
    )

    fecha = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now,
    )

    metodo_pago_anterior_id = fields.Many2one(
        "pos.payment.method",
        string="Metodo Anterior",
        required=True,
    )

    metodo_pago_nuevo_id = fields.Many2one(
        "pos.payment.method",
        string="Metodo Nuevo",
        required=True,
    )

    monto = fields.Float(
        string="Monto",
        required=True,
    )

    motivo = fields.Text(
        string="Motivo",
        required=True,
    )

    estado = fields.Selection(
        [
            ("draft", "Borrador"),
            ("aprobado", "Aprobado"),
            ("cancelado", "Cancelado"),
        ],
        default="draft",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        order_id = self.env.context.get("default_pos_order_id")
        if not order_id:
            return res

        order = self.env["pos.order"].browse(order_id)

        if order.payment_ids:
            payment = order.payment_ids[0]
            res.update(
                {
                    "metodo_pago_anterior_id": payment.payment_method_id.id,
                    "monto": payment.amount,
                }
            )

        return res

    def action_aprobar_correccion(self):
        for rec in self:

            order = rec.pos_order_id

            if order.session_id and order.session_id.state == "closed":
                raise UserError(
                    "No se puede corregir el método de pago porque la sesión POS ya está cerrada."
                )

            doc_type = getattr(order, "sunat_document_type", False)
            sunat_state = getattr(order, "sunat_state", False)

            # FACTURAS
            if doc_type == "01":
                raise UserError(
                    "No se permite corregir pagos en facturas electrónicas."
                )

            # BOLETAS YA ENVIADAS
            if doc_type == "03" and sunat_state in ["enviado", "aceptado"]:
                raise UserError(
                    "La boleta ya fue enviada a SUNAT y no puede corregirse."
                )

            if len(order.payment_ids) != 1:
                raise UserError(
                    "Esta orden tiene múltiples métodos de pago. "
                    "Por seguridad no se puede corregir desde este modulo. "
                    "Debe revisarse mediante anulación controlada."
                )

            correccion_previa = self.search(
                [
                    ("pos_order_id", "=", order.id),
                    ("estado", "=", "aprobado"),
                    ("id", "!=", rec.id),
                ],
                limit=1,
            )

            if correccion_previa:
                raise UserError(
                    "Esta orden ya tiene una corrección de pago aplicada. "
                    "No se permite corregirla nuevamente sin revisión administrativa."
                )

            payment = order.payment_ids[0]

            if rec.metodo_pago_anterior_id == rec.metodo_pago_nuevo_id:
                raise UserError(
                    "El nuevo método de pago debe ser diferente al anterior."
                )

            payment.write({"payment_method_id": rec.metodo_pago_nuevo_id.id})

            rec.estado = "aprobado"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Corrección aplicada",
                "message": "El método de pago fue actualizado correctamente.",
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window_close",
                },
            },
        }


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_open_payment_correction(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Corregir método de pago",
            "res_model": "pos.payment.correction",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pos_order_id": self.id,
            },
        }
