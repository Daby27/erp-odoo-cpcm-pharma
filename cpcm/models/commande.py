# cpcm/models/commande.py
from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
import base64


class CpcmCommande(models.Model):
    _name = 'cpcm.commande'
    _description = 'Commande'
    _order = 'date desc'
    _rec_name = 'client_id'
    _inherit = ['mail.thread']


    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        ondelete='cascade',
    )
    vmc_id = fields.Many2one(
        'res.users',
        string='VMC responsable',
        default=lambda self: self.env.user,
        ondelete='set null'
    )

    date = fields.Date(string='Date de commande', default=fields.Date.today)

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
        ('validated', 'Confirmée'),
        ('rejected', 'Rejetée'),
    ], string="État", default='draft', track_visibility='onchange')

    #acheminer la commande vers un grossiste (intermédiaire logistique).
    grossiste_id = fields.Many2one(
        'res.partner',
        string="Grossiste",
        domain="[('function', '=', 'Grossiste médical')]",
        help="Grossiste sélectionné pour exécuter cette commande."
    )

    # Bouton pour VMC : envoyer à l’ADV
    def action_submit_to_adv(self):
        for rec in self:
            if not rec.ligne_commande_ids:
                raise ValidationError("Impossible d'envoyer une commande sans lignes de produit.")
            rec.state = 'submitted'



    # Bouton ADV : valider

    def action_adv_validate(self):
        for rec in self:
            if not rec.grossiste_id:
                raise ValidationError("Veuillez sélectionner un grossiste avant de valider la commande.")

            rec.state = 'validated'

            template_id = self.env.ref('cpcm.email_template_commande_vmc', raise_if_not_found=False)

            if template_id:
                # Générer le contenu PDF

                pdf_content = self.env['ir.actions.report'].sudo()._get_report_from_name('cpcm.report_bon_commande_document').render_qweb_pdf( [rec.id])[0]

                # Créer une pièce jointe PDF
                attachment = self.env['ir.attachment'].create({
                    'name': f'Bon de commande - {rec.client_id.name}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'cpcm.commande',
                    'res_id': rec.id,
                    'mimetype': 'application/pdf',
                })

                # Envoyer l'email avec la pièce jointe
                template_id.send_mail(
                    rec.id,
                    force_send=True,
                    email_values={
                        'email_to': rec.client_id.email,
                        # Ajouter un champ email du grossiste dans le mail de validation 
                        #'email_to': ','.join(filter(None, [rec.client_id.email, rec.grossiste_id.email])),
                        'email_from': 'nawelbg23@gmail.com',
                        'reply_to': 'nawelbg23@gmail.com',
                        'author_id': False,  # empêche l'utilisation de l’e-mail de l’utilisateur connecté
                        'attachment_ids': [attachment.id],
                    }
                )


                #  Ajouter une trace dans le chatter (le mail et pdf attaché) :
                rec.message_post(
                    body=f"Le bon de commande a été validé et envoyé par email avec la pièce jointe.<br/>Email envoyé à: {rec.client_id.email}<br/>Contenu: {template_id.body_html}",
                    attachment_ids=[attachment.id]
                )

            # 🔁 Retirer les quantités du stock du grossiste concerné
            for ligne in rec.ligne_commande_ids:
                produit_stock = self.env['cpcm.produit.stock'].search([
                    ('product_id', '=', ligne.product_id.id),
                    ('grossiste_id', '=', rec.grossiste_id.id)
                ], limit=1)

                if not produit_stock:
                    raise ValidationError(
                        f"Le produit '{ligne.product_id.display_name}' n'existe pas dans le stock du grossiste '{rec.grossiste_id.name}'."
                    )

                produit_stock.retirer_du_stock(ligne.quantity)

            rec.message_post(
                        body="Les produits ont été retirés du stock du grossiste après validation de la commande.")

    # Bouton ADV : rejeter
    def action_adv_reject(self):
        for rec in self:
            rec.state = 'rejected'

    # L'ADV ne doit voir que les commandes NON brouillon
    def _search(self, domain, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if self.env.user.has_group('cpcm.group_adv'):
            domain = expression.AND([domain, [('state', '!=', 'draft')]])
        return super(CpcmCommande, self)._search(domain, offset=offset,
                                                 limit=limit, order=order, count=count,
                                                 access_rights_uid=access_rights_uid)

    #empêcher un VMC de modifier une commande une fois qu’elle est passée en état submitted ou aprè
    def write(self, vals):
        for record in self:
            if self.env.user.has_group('cpcm.group_vmc') and record.state != 'draft':
                raise UserError("Vous ne pouvez pas modifier une commande une fois qu'elle a été soumise.")
        return super(CpcmCommande, self).write(vals)

    #empêcher un VMC de supprimer une commande soumise
    def unlink(self):
        for record in self:
            if self.env.user.has_group('cpcm.group_vmc') and record.state != 'draft':
                raise UserError("Vous ne pouvez pas supprimer une commande une fois qu'elle a été soumise.")
        return super(CpcmCommande, self).unlink()

    # Lignes de commande : produit + quantité
    ligne_commande_ids = fields.One2many(
        'cpcm.commande.ligne',
        'commande_id',
        string="Lignes de Commande"
    )

    montant_total = fields.Monetary(
        string='Montant Total',
        compute='_compute_montant_total',
        store=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
    )

    #Nom de la societé qu'on relie a report_bon_commande_document
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
        readonly=True
    )





    @api.depends('ligne_commande_ids.subtotal')
    def _compute_montant_total(self):
        for record in self:
            record.montant_total = sum(line.subtotal for line in record.ligne_commande_ids)


class CpcmCommandeLigne(models.Model):
    _name = 'cpcm.commande.ligne'
    _description = "Ligne de Commande"

    commande_id = fields.Many2one(
        'cpcm.commande',
        string='Commande',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True
    )
    quantity = fields.Float(string='Quantité', default=1.0)
    price_unit = fields.Float(
        string='Prix Unitaire',
        related='product_id.lst_price',
        readonly=True
    )
    subtotal = fields.Monetary(
        string='Sous-total',
        compute='_compute_subtotal',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='commande_id.currency_id',
        readonly=True
    )

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
