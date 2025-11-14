from datetime import datetime, timedelta
from odoo import models, fields , api
from odoo.exceptions import ValidationError , UserError
import json
from odoo.osv import expression

class CpcmTournee(models.Model):
    _name = 'cpcm.tournee'
    _description = 'Plan de tournée'

    name = fields.Char(string='Nom du plan', required=True)
    vmc_id = fields.Many2one('res.users', string="VMC", required=True)
    date_debut = fields.Date(string="Début de la tournée", required=True)
    date_fin = fields.Date(string="Fin de la tournée", required=True)
    ligne_ids = fields.One2many('cpcm.tournee.jour', 'tournee_id', string="Jours de tournée")
    #jours_ids = fields.One2many('cpcm.jour', 'tournee_id', string='jours')
    client_ids = fields.Many2many('res.partner', string='Clients prévus')

    #pour valider
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'transmis'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
    ], string='État', default='draft', tracking=True)


    jours_feries_ids = fields.Many2many(
        'calendrier.jour_ferie',
        string="Jours fériés inclus"
    )

    @api.onchange('date_debut', 'date_fin')
    def _onchange_dates_auto_feries(self):
        """Version optimisée pour Odoo 13"""
        self.ensure_one()  # Sécurité supplémentaire

        if not (self.date_debut and self.date_fin):
            return {}

        # 1. Nettoyage des anciennes relations
        self.jours_feries_ids = [(5, 0, 0)]

        # 2. Recherche avec domain optimisé
        feries = self.env['calendrier.jour_ferie'].search([
            ('date', '>=', self.date_debut),
            ('date', '<=', self.date_fin)
        ], order='date ASC')  # 'order' améliore les perfs

        # 3. Mise à jour conditionnelle
        if feries:
            self.jours_feries_ids = [(6, 0, feries.ids)]
            return {
                'warning': {
                    'title': "Jours fériés mis à jour",
                    'message': f"{len(feries)} jour(s) inclus(s)",
                }
            }
        return {}


    jours_couvrables_ids = fields.Many2many(
        'cpcm.jour',
        string='Jours couvrables'
    )

    # Affiche une erreur IMMÉDIATE si date_debut > date_fin
    @api.onchange('date_debut', 'date_fin')
    def _onchange_dates_strict(self):
        if self.date_debut and self.date_fin and self.date_debut > self.date_fin:
            raise UserError("🚨 Impossible : la date de début doit être avant la fin !")


    #Soumettre le plan du tournee au superviseur pour validation
    def action_submit(self):
        for rec in self:
            if not rec.ligne_ids:
                raise ValidationError("Veuillez générer les jours de tournée avant de valider.")
            rec.state = 'submitted'

    #valider la tournee
    def action_validate_plan_tournee(self):
        for rec in self:
            rec.state='validated'

    #rejeter un plan du tournee:
    def action_reject_plan_tournee(self):
        for rec in self:
            rec.state='rejected'

    ##########################################
    def generer_jours_tournee(self):
        """Ouvre un popup de confirmation avant génération"""
        self.ensure_one()

        # Calcul des dates qui seront générées (identique à avant)
        dates_a_generer = []
        jours_feries_dates = {ferie.date for ferie in self.jours_feries_ids}
        jours_couvrables_names = {jour.name.lower() for jour in self.jours_couvrables_ids}

        date_courante = fields.Date.from_string(self.date_debut)
        date_fin = fields.Date.from_string(self.date_fin)

        while date_courante <= date_fin:
            jour_semaine = date_courante.strftime("%A").lower()
            if (jour_semaine in jours_couvrables_names and
                    date_courante not in jours_feries_dates):
                dates_a_generer.append(date_courante)
            date_courante += timedelta(days=1)

        # Ouvre un popup de confirmation
        # NOTE :
        # Cette action ouvre normalement un wizard 'cpcm.tournee.confirmation'.
        # Le wizard n'est pas inclus dans cette version publique du code.
        # Il sert uniquement à confirmer la génération des dates de tournée.

        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmer la génération',
            'res_model': 'cpcm.tournee.confirmation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tournee_id': self.id,
                'default_dates_a_generer': json.dumps([fields.Date.to_string(d) for d in dates_a_generer]),
            }
        }


    # Le superviseur ne doit voir que les commandes NON brouillon
    def _search(self, domain, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        # Si l'utilisateur est superviseur, on filtre les brouillons
        if self.env.user.has_group('cpcm.group_superviseur'):
            domain = expression.AND([domain, [('state', '!=', 'draft')]])
        return super(CpcmTournee, self)._search(domain, offset=offset, limit=limit,
                                                order=order, count=count,
                                                access_rights_uid=access_rights_uid)
        



################################################################
#class jour pour generer les jours couvrable

class Jour(models.Model):
    _name = 'cpcm.jour'
    _description = 'Jour de la semaine'
    name = fields.Char(string='Jour', required=True)


class CpcmTourneeJour(models.Model):
    _name = 'cpcm.tournee.jour'
    _description = 'Jour de tournée'
    _rec_name = 'date'

    date = fields.Date(string="Date", required=True)
    localite = fields.Char(string="Localité")

    pharmacie_ids = fields.Many2many(
        'res.partner',
        relation='cpcm_tournee_jour_pharmacie_rel',  # Table de relation unique
        column1='tournee_jour_id',  # Colonne pour cpcm.tournee.jour
        column2='partner_id',  # Colonne pour res.partner
        string='Pharmacies',
        domain="[('function', '=', 'Pharmacie')]"
    )
    structure_medicale_ids = fields.Many2many(
        'res.partner',
        relation='cpcm_tournee_jour_structure_medicale_rel',  # Table de relation unique
        column1='tournee_jour_id',
        column2='partner_id',
        string='Structures médicales',
        domain="[('function', '=', 'Structure médicale')]"
    )
    medecin_ids = fields.Many2many(
        'res.partner',
        relation='cpcm_tournee_jour_medecin_rel',  # Table de relation unique
        column1='tournee_jour_id',
        column2='partner_id',
        string='Médecins',
        domain="[('function', '=', 'Médecin')]"
    )
    grossiste_observation_ids = fields.Many2many(
        'res.partner',
        relation='cpcm_tournee_jour_grossiste_rel',  # Table de relation unique
        column1='tournee_jour_id',
        column2='partner_id',
        string='Grossistes médicaux',
        domain="[('function', '=', 'Grossiste médical')]"
    )


    tournee_id = fields.Many2one('cpcm.tournee', string="Plan de tournée", ondelete='cascade')
