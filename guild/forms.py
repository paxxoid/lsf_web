from django import forms

from .models import GuildApplication


class GuildApplicationForm(forms.ModelForm):
    class Meta:
        model = GuildApplication
        fields = [
            "character_name",
            "class_name",
            "level",
            "discord_name",
            "timezone_name",
            "typical_play_times",
            "experience",
            "why_join",
        ]
        widgets = {
            "experience": forms.Textarea(attrs={"rows": 4}),
            "why_join": forms.Textarea(attrs={"rows": 5}),
        }
