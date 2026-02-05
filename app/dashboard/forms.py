"""
IMAS Manager - Dashboard Forms

Forms for incident management interface.
"""
from __future__ import annotations

from django import forms

from core.choices import IncidentSeverity
from core.models import ImpactScope, Incident, Service


class IncidentCreateForm(forms.ModelForm):
    """
    Form for creating a new incident.
    """

    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        label="Service impacté",
        help_text="Sélectionnez le service technique affecté.",
    )

    severity = forms.ChoiceField(
        choices=IncidentSeverity.choices,
        initial=IncidentSeverity.SEV3_MEDIUM,
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        label="Sévérité",
        help_text="SEV1 = Critique, SEV2 = Haute, SEV3 = Moyenne, SEV4 = Basse",
    )

    impacted_scopes = forms.ModelMultipleChoiceField(
        queryset=ImpactScope.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple(attrs={
            "class": "form-check-input",
        }),
        required=False,
        label="Périmètres impactés",
        help_text="Cochez les périmètres fonctionnels touchés (Légal, Sécurité, PR...).",
    )

    class Meta:
        model = Incident
        fields = ["title", "description", "service", "severity", "impacted_scopes"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ex: Indisponibilité API Paiements",
                "autofocus": True,
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Décrivez le problème observé, les symptômes, l'impact utilisateur...",
            }),
        }
        labels = {
            "title": "Titre de l'incident",
            "description": "Description",
        }

    def clean_title(self) -> str:
        """Validate title is not too short."""
        title = self.cleaned_data.get("title", "")
        if len(title) < 10:
            raise forms.ValidationError(
                "Le titre doit contenir au moins 10 caractères."
            )
        return title


class IncidentNoteForm(forms.Form):
    """
    Form for adding a note to an incident timeline.
    """

    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Ajoutez une note ou un commentaire...",
        }),
        label="Note",
        min_length=5,
        max_length=2000,
    )


class IncidentResolveForm(forms.Form):
    """
    Form for resolving an incident.
    """

    resolution_note = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Décrivez la résolution : cause identifiée, actions correctives...",
        }),
        label="Note de résolution",
        required=False,
        max_length=5000,
    )

    root_cause = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Quelle était la cause profonde de cet incident ?",
        }),
        label="Cause racine",
        required=False,
        max_length=2000,
    )

    confirm = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
        label="Je confirme que l'incident est résolu",
        required=True,
    )


class IncidentFilterForm(forms.Form):
    """
    Form for filtering incidents list.
    """

    status = forms.ChoiceField(
        choices=[("", "Tous les statuts")] + list(IncidentSeverity.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    severity = forms.ChoiceField(
        choices=[("", "Toutes les sévérités")] + list(IncidentSeverity.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True),
        required=False,
        empty_label="Tous les services",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm",
            "placeholder": "Rechercher...",
        }),
    )
