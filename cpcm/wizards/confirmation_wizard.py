from odoo import models, fields, api
import json

class TourneeConfirmation(models.TransientModel):
    _name = 'cpcm.tournee.confirmation'
    _description = 'Confirmation génération jours'

    tournee_id = fields.Many2one('cpcm.tournee', required=True)
    dates_a_generer = fields.Text()  # Stocke les dates en JSON

    def action_confirmer(self):
        """Crée les jours après confirmation"""
        dates = json.loads(self.dates_a_generer)
        tournee = self.tournee_id

        # Supprime les anciennes lignes
        tournee.ligne_ids.unlink()

        # Crée les nouvelles lignes
        for date_str in dates:
            self.env['cpcm.tournee.jour'].create({
                'date': date_str,
                'tournee_id': tournee.id,
                'localite': '',
                # ... autres champs
            })

        return {'type': 'ir.actions.act_window_close'}
