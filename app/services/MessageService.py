#!/usr/bin/env python3
from datetime import datetime
import random
from app.services.PresenceLevelService import PresenceLevel


class MessageService:
    def __init__(self):
        self.seasonal_messages = {
            "spring": {
                PresenceLevel.EMPTY: [
                    "Frühlingserwachen! Der erste warme Tag - wer spielt mit? 🌸",
                    "Die Saison beginnt! Sei dabei beim ersten Spiel im Frühling!",
                ],
                PresenceLevel.FEW: [
                    "Frühlingsgefühle am Beachfeld! Komm zur kleinen Runde!",
                    "Die ersten Sonnenstrahlen locken Spieler raus - sei dabei!",
                ],
                PresenceLevel.MANY: [
                    "Frühlingsfieber! Das Feld ist voller Energie!",
                    "Osterspecial: Volleyball-Marathon im Gange! 🐰",
                ],
            },
            "summer": {
                PresenceLevel.EMPTY: [
                    "Perfekter Badetag! Erst Volleyball, dann in den Kaufbach springen! 💦",
                    "Sommerhitze? Abkühlung mit Beachvolleyball und kühlen Getränken! 🍹",
                ],
                PresenceLevel.FEW: [
                    "Sommerliche Chillrunde - wer macht mit? ☀️",
                    "Kleine Gruppe genießt die Abendsonne - komm dazu!",
                ],
                PresenceLevel.MANY: [
                    "Sommerparty! Volleyball bis die Sonne untergeht! 🌅",
                    "Volles Haus! Sideout-Turnier mit Grill-Special! 🍖",
                ],
            },
            "autumn": {
                PresenceLevel.EMPTY: [
                    "Herbststille? Mach das Feld wieder lebendig! 🍂",
                    "Goldener Oktober - perfekt für eine entspannte Runde!",
                ],
                PresenceLevel.FEW: [
                    "Gemütliche Herbstrunde mit Lagerfeueratmosphäre! 🔥",
                    "Die Blätter fallen, wir spielen weiter - komm vorbei!",
                ],
                PresenceLevel.MANY: [
                    "Herbstfest-Stimmung! Volleyball und heiße Getränke! 🍁",
                    "Volles Haus trotz kühlerer Temperaturen - Respekt!",
                ],
            },
            "winter": {
                PresenceLevel.EMPTY: [
                    "Winter-Challenge: Wer traut sich bei der Kälte? ❄️",
                    "Einsamer Schneemann sucht Volleyballpartner! ⛄",
                ],
                PresenceLevel.FEW: [
                    "Hartgesottene Winter-Spieler am Start! 🔥",
                    "Kleine Runde trotz Kälte - echtes Commitment!",
                ],
                PresenceLevel.MANY: [
                    "Winter-Wunder! So viele hartgesottene Spieler!",
                    "Volles Haus und warme Stimmung trotz Frost! ☕",
                ],
            },
        }

        self.time_messages = {
            "morning": {
                PresenceLevel.EMPTY: [
                    "Frühaufsteher gesucht für die erste Morgenrunde! 🌄",
                    "Morgenstund hat Gold im Mund - und freie Plätze!",
                ],
                PresenceLevel.FEW: [
                    "Early Birds am Ball - wer macht das Match komplett?",
                    "Morgenfrische und ein paar motivierte Spieler - perfekt!",
                ],
                PresenceLevel.MANY: [
                    "Volles Haus am Morgen - Energie pur! ⚡",
                    "Frühsport mit Volleyball - beeindruckende Beteiligung!",
                ],
            },
            "day": {
                PresenceLevel.EMPTY: [
                    "Mittagspause? Perfekt für eine schnelle Runde!",
                    "Freie Plätze in der Tagessonne - schnapp dir einen!",
                ],
                PresenceLevel.FEW: [
                    "Gemütliche Tagessession - ideal für Neueinsteiger!",
                    "Kleine Gruppe beim Lunchtime-Volleyball",
                ],
                PresenceLevel.MANY: [
                    "Tagestrubel am Beachfeld - volle Action!",
                    "Nachmittags-Marathon mit vielen Spielern im Wechsel!",
                ],
            },
            "evening": {
                PresenceLevel.EMPTY: [
                    "Abendstille? Bring Leben ins Spiel! 🌆",
                    "Perfekter Zeitpunkt für ein entspanntes Abendspiel",
                ],
                PresenceLevel.FEW: [
                    "Abendliche Chill-Session mit Lagerfeuer 🔥",
                    "Sunset-Volleyball mit kleiner Gruppe - magisch!",
                ],
                PresenceLevel.MANY: [
                    "Grillabend mit Volleyball - perfekter Feierabend! 🍢",
                    "Volles Haus bei Abenddämmerung - Party-Stimmung!",
                ],
            },
            "night": {
                PresenceLevel.EMPTY: [
                    "Nachtruhe? Nicht mit uns! Lagerfeuer gefällig? 🌕",
                    "Einsame Nachteule sucht Mitternachts-Mitspieler!",
                ],
                PresenceLevel.FEW: [
                    "Spätnachts-Special mit paar Nachtschwärmern! 🌙",
                    "Under the Lights: Kleine aber feines Beisammen sitzen",
                ],
                PresenceLevel.MANY: [
                    "Party am Laufen - komm ran! 🔥",
                    "Volles Haus bis spät in die Nacht - Legenden!",
                ],
            },
        }

        self.base_messages = {
            PresenceLevel.EMPTY: [
                "Leeres Feld = Deine Chance! Eröffne die Spielsession!",
                "Keine Warteschlange - sofort losspielen! 🏐",
                "Die Netze warten auf dich!",
                "Möglicherweise ist niemand da. Schau doch vorbei!",
                "Alle Plätze frei - dein Spiel, deine Regeln!",
                "Perfekter Moment für ein Privattraining!",
            ],
            PresenceLevel.FEW: [
                "Kleine Runde am Start - perfekt für schnelle Spiele!",
                "Ideal um neue Spielpartner kennenzulernen!",
                "Ein paar Spieler unterwegs - mach das Match komplett!",
                "Gemütliche Atmosphäre mit wenigen Leuten",
                "Kleine Gruppe sucht Verstärkung!",
                "Genug für ein Spiel, aber noch Platz für dich!",
            ],
            PresenceLevel.MANY: [
                "Volles Haus! Sideout-Turnier oder Party? 🎉",
                "Action pur zwischen Spielen und Grillen!",
                "Der Sand brodelt vor Energie!",
                "Großes Gedränge - beste Stimmung!",
                "Viele Spieler, gute Laune - sei dabei!",
                "Turnieratmosphäre - wer ist heute der Champion?",
            ],
        }

        self.combo_messages = [
            "Netz frei? Spielen! Pause? Grillen! Lust? Kaufbach-Sprung! 💦",
            "Volleyball → Grillen → Chillen → Repeat!",
            "Dein Tag im Fribbe: Spielen, Schwimmen, Sonnen!",
            "Beachvolleyball mit allen Extras: Feuer, Grill, Musik!",
            "Sideouts, Cocktails, Lagerfeuer - das volle Programm!",
            "Von morgens bis abends: Volleyball in allen Varianten!",
            "Das perfekte Beach-Life: Spiel, Spaß, Entspannung!",
        ]

    def get_season(self, last_updated: datetime) -> str:
        month = last_updated.month
        if 3 <= month <= 5:
            return "spring"
        elif 6 <= month <= 8:
            return "summer"
        elif 9 <= month <= 11:
            return "autumn"
        else:
            return "winter"

    def get_daytime(self, last_updated: datetime) -> str:
        hour = last_updated.hour
        if 5 <= hour < 10:
            return "morning"
        elif 10 <= hour < 16:
            return "day"
        elif 16 <= hour < 22:
            return "evening"
        else:
            return "night"

    def get_message(self, status: PresenceLevel, last_updated: datetime) -> str:
        # 20% Chance für einen Kombi-Spruch
        if random.random() < 0.2:
            return random.choice(self.combo_messages)

        # 40% Chance für saisonale oder tageszeitabhängige Nachricht
        if random.random() < 0.4:
            daytime = self.get_daytime(last_updated)
            if daytime in self.time_messages and status in self.time_messages[daytime]:
                return random.choice(self.time_messages[daytime][status])

            season = self.get_season(last_updated)
            if (
                season in self.seasonal_messages
                and status in self.seasonal_messages[season]
            ):
                return random.choice(self.seasonal_messages[season][status])

        # Fallback zu den Basis-Nachrichten (40% Chance)
        return random.choice(self.base_messages[status])
