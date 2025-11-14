# -*- coding: utf-8 -*-

from odoo import models, fields, api
#from datetime import datetime
from odoo.exceptions import ValidationError

class CpcmVisite(models.Model):
    _name = 'cpcm.visite'
    _description = 'Visite effectuée pendant une tournée'
    #_order = 'date_visite desc'

    name = fields.Char(string='Référence', copy=False, readonly=True)
    plan_id = fields.Many2one('cpcm.tournee', string='Plan de tournée', required=True)
    vmc = fields.Many2one(
        'res.users',
        related='plan_id.vmc_id',
        string='VMC',
        readonly=True,
        store=True
    )
    jour_id = fields.Many2one(
        'cpcm.tournee.jour',
        string="Jour de tournée",
        domain="[('tournee_id', '=', plan_id)]",  # filtre par plan sélectionné
        required=True
    )


    #faire des liens
    ligne_ids = fields.One2many('cpcm.visite.ligne', 'visite_id', string="Clients à visiter")

    remarques = fields.Text(string='Remarques')

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Effectuée'),
        ('cancel', 'Annulée'),
    ], string='Statut', default='draft', tracking=True)


    @api.model
    def create(self, vals):
        # On a besoin du plan pour trouver le VMC
        plan = self.env['cpcm.tournee'].browse(vals.get('plan_id')) if vals.get('plan_id') else None
        jour = self.env['cpcm.tournee.jour'].browse(vals.get('jour_id')) if vals.get('jour_id') else None

        # Date de la visite : jour.date ou aujourd’hui
        if jour and hasattr(jour, 'date') and jour.date:
            date_visite = jour.date
        else:
            date_visite = fields.Datetime.now()

        jour_str = date_visite.strftime('%A %d %B').capitalize()  # Exemple : Lundi 24 Juin
        vmc_name = plan.vmc_id.name if plan and plan.vmc_id else "VMC ?"

        # Nom final
        vals['name'] = f"Visite {jour_str} - {vmc_name}"

        return super(CpcmVisite, self).create(vals)

    def action_marquer_effectuee(self):
        for rec in self:
            if not rec.ligne_ids:
                raise ValidationError("Aucune ligne de visite n’a été planifiée.")
            rec.state = 'done'
        """
        self.write({
            'state': 'done',
            'date_visite': datetime.now(),
        })
        """





    def action_annuler_visite(self):
        self.write({'state': 'cancel'})


    # Automatiser le remplissage des clients prévus lors du choix du jour
    @api.onchange('jour_id')
    def _onchange_jour_id(self):
        if not self.jour_id:
            return

        lignes = []

        for partenaire in self.jour_id.medecin_ids:
            lignes.append((0, 0, {
                'partner_id': partenaire.id,
                'type_client': 'medecin'
            }))
        for partenaire in self.jour_id.pharmacie_ids:
            lignes.append((0, 0, {
                'partner_id': partenaire.id,
                'type_client': 'pharmacie'
            }))
        for partenaire in self.jour_id.structure_medicale_ids:
            lignes.append((0, 0, {
                'partner_id': partenaire.id,
                'type_client': 'structure'
            }))
        for partenaire in self.jour_id.grossiste_observation_ids:
            lignes.append((0, 0, {
                'partner_id': partenaire.id,
                'type_client': 'grossiste'
            }))

        print(">>> LIGNES GÉNÉRÉES :", lignes)  # ← Ajoute ceci temporairement

        self.ligne_ids = lignes
        


class CpcmVisiteLigne(models.Model):
    _name = 'cpcm.visite.ligne'
    _description = 'Ligne de visite'

    visite_id = fields.Many2one('cpcm.visite', string='Visite', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Client', required=True)
    type_client = fields.Selection([
        ('medecin', 'Médecin'),
        ('pharmacie', 'Pharmacie'),
        ('structure', 'Structure médicale'),
        ('grossiste', 'Grossiste médical')
    ], string="Type")

    visite_effectuee = fields.Boolean(string="Visite effectuée")
    visite_annuler = fields.Boolean(string="Visite annulée")
    heure = fields.Datetime(string="Heure d'action")
    raison_annulation = fields.Text(string="Raison de l'annulation")

    @api.model
    def create(self, vals):
        if vals.get('visite_effectuee') or vals.get('visite_annuler'):
            vals['heure'] = fields.Datetime.now()
        return super().create(vals)

    def write(self, vals):
        if ('visite_effectuee' in vals and vals['visite_effectuee']) or ('visite_annuler' in vals and vals['visite_annuler']):
            vals['heure'] = fields.Datetime.now()
        return super().write(vals)
