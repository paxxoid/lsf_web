from django.shortcuts import render


def home(request):
    return render(
        request,
        "guild/home.html",
        {
            "guild_name": "Loot and Some Fun",
            "server_name": "Project Quarm",
        },
    )