import random
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app import env
from app.services.occupancy.model import OccupancyType
from app.services.presence_level import PresenceLevel
from app.services.weather_service import Temperature, Weather, WeatherState

# Season month boundaries (inclusive)
_SPRING_START, _SPRING_END = 3, 5
_SUMMER_START, _SUMMER_END = 6, 8
_AUTUMN_START, _AUTUMN_END = 9, 11

# Daytime hour boundaries
_MORNING_START, _MORNING_END = 5, 10
_DAY_START, _DAY_END = 10, 16
_EVENING_START, _EVENING_END = 16, 22

# Random thresholds for message selection
_WEATHER_MSG_CHANCE = 0.3
_COMBO_MSG_CHANCE = 0.2
_SEASONAL_MSG_CHANCE = 0.4


@dataclass
class StatusMessage:
    """A human-readable status message."""

    message: str


@dataclass
class PushMessage(StatusMessage):
    """A push notification with title and body."""

    title: str


class MessageService:
    """Generate randomized German-language status and push messages."""

    def __init__(self) -> None:
        self.occupied_messages = [
            "Heute ({ftime}) ist das Fribbe leider durch eine Veranstaltung belegt.",
            "Die Felder sind heute ({ftime}) leider nicht verfügbar.",
        ]

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

        self.push_titles: dict[PresenceLevel, list[str]] = {
            PresenceLevel.FEW: [
                "Erster Aufschlag im Fribbe! 🏐",
                "Die ersten Spieler sind da! 🏐",
                "Es geht los im Fribbe! 🏐",
                "Kleine Runde im Fribbe! 🏐",
            ],
            PresenceLevel.MANY: [
                "Heute ist richtig was los im Fribbe! 🏐",
                "Voll besetzt im Fribbe! 🏐",
                "Der Sand bebt im Fribbe! 🏐",
                "Party am Fribbe! 🏐",
            ],
        }

        self.temperature_messages: dict[Temperature, dict[PresenceLevel, list[str]]] = {
            Temperature.HOT: {
                PresenceLevel.EMPTY: [
                    "Hitzerekord! Erst Volleyball, dann direkt in den Kaufbach! 💦",
                    "So heiß - aber das Feld ist frei! 🌡️ Wer traut sich?",
                    "Tropische Temperaturen, freier Sand - die perfekte Beach-Session!",
                ],
                PresenceLevel.FEW: [
                    "Trotz der Hitze sind schon ein paar Mutige am Ball! 🌡️",
                    "Heiß, heiß, heiß - kleine Runde hält durch! ☀️",
                    "Sommerhitze trifft Beachvolleyball - Respekt!",
                ],
                PresenceLevel.MANY: [
                    "Hitzewelle trifft volles Feld - echte Beachvolleyball-Stimmung! ☀️",
                    "So heiß und trotzdem volles Haus - ihr seid unglaublich! 🌡️",
                    "Sommerparty im Fribbe! Heute wird geschwitzt und gespielt! 🏖️",
                ],
            },
            Temperature.WARM: {
                PresenceLevel.EMPTY: [
                    "Perfektes Wetter, freier Sand - jetzt einsteigen! ☀️",
                    "Traumwetter und keine Warteschlange - selten! 🌞",
                    "Warmer Tag, leerer Platz - deine Einladung!",
                ],
                PresenceLevel.FEW: [
                    "Herrliches Wetter, kleine Runde - genieß die Sonne! 🌤️",
                    "Warme Temperaturen und ein paar Spieler - perfekte Kombination!",
                    "Tolles Wetter lockt die ersten Spieler raus - mach mit! ☀️",
                ],
                PresenceLevel.MANY: [
                    "Tolles Wetter, voller Platz - Sommerfeeling pur! 🌞",
                    "Bei diesem Traumwetter ist richtig was los! ☀️",
                    "Warmer Abend, volles Feld - so muss das sein! 🏐",
                ],
            },
            Temperature.MILD: {
                PresenceLevel.EMPTY: [
                    "Angenehme Temperaturen, freier Sand - ideal zum Spielen!",
                    "Mildes Wetter, kein Gedränge - komm einfach vorbei! 🌥️",
                    "Perfekte Bedingungen für entspanntes Volleyball!",
                ],
                PresenceLevel.FEW: [
                    "Schöner milder Tag, ein paar Spieler schon am Start!",
                    "Angenehmes Wetter, kleine Gruppe - noch Platz für dich! 🌤️",
                    "Milde Temperaturen, gute Stimmung - komm dazu!",
                ],
                PresenceLevel.MANY: [
                    "Tolles mildes Wetter hat viele rausgelockt! 🌤️",
                    "Angenehm mild und voller Platz - herrlicher Abend!",
                    "Mildes Wetter, beste Stimmung - alle sind dabei!",
                ],
            },
            Temperature.COLD: {
                PresenceLevel.EMPTY: [
                    "Kalt, aber das Feld wartet! Für echte Hartgesottene! 🥶",
                    "Frostige Temperaturen = freier Sand. Trau dich! ❄️",
                    "Wer braucht schon Wärme? Das Feld ist frei! 🥶",
                ],
                PresenceLevel.FEW: [
                    "Trotz der Kälte am Ball - das ist Leidenschaft! 🔥",
                    "Kleine aber mutige Gruppe trotzt dem Frost! ❄️",
                    "Kalt draußen, heiß am Netz - Respekt! 🏐",
                ],
                PresenceLevel.MANY: [
                    "Das Feld trotzt der Kälte - ihr seid unaufhaltbar! ❄️",
                    "Voller Platz trotz Minusgraden - absolute Legenden! 🥶",
                    "Kalt wie draußen, heiß wie die Stimmung - Wahnsinn! 🔥",
                ],
            },
        }

        self.weather_state_messages: dict[WeatherState, dict[PresenceLevel, list[str]]] = {
            WeatherState.CLEAR: {
                PresenceLevel.EMPTY: [
                    "Klare Sicht, freier Sand - perfektes Volleyballwetter! ☀️",
                    "Sonnenschein und leeres Feld - deine Chance auf ein Match! 🌞",
                    "Strahlend blauer Himmel, keine Warteschlange - los geht's! ☀️",
                ],
                PresenceLevel.FEW: [
                    "Sonnenschein und eine kleine Gruppe - perfekte Kombination! 🌤️",
                    "Klare Sicht, gute Stimmung - komm dazu! ☀️",
                    "Tolles Wetter und ein paar Spieler am Start - ideal! 🌞",
                ],
                PresenceLevel.MANY: [
                    "Sonnenschein und volles Feld - Sommerfeeling pur! 🌞",
                    "Bei diesem Traumwetter ist richtig was los! ☀️",
                    "Warmer Abend, volles Feld - so muss das sein! 🏐",
                ],
            },
            WeatherState.CLOUDY: {
                PresenceLevel.EMPTY: [
                    "Bewölkt, aber das Feld ist frei - perfektes Wetter für ein Spiel! ☁️",
                    "Keine Sonne, aber auch keine Warteschlange - deine Chance! 🌥️",
                    "Wolkig, aber freier Sand - ideal für entspanntes Volleyball! ☁️",
                ],
                PresenceLevel.FEW: [
                    "Bewölkter Himmel, aber eine kleine Gruppe am Start - komm dazu! 🌤️",
                    "Wolkig, aber gute Stimmung - perfekt für eine Runde! ☁️",
                    "Trotz der Wolken am Ball - das ist Leidenschaft! 🔥",
                ],
                PresenceLevel.MANY: [
                    "Bewölkt, aber volles Feld - echte Beachvolleyball-Stimmung! ☁️",
                    "So bewölkt und trotzdem volles Haus - ihr seid unglaublich! 🌥️",
                    "Wolkiger Abend, volles Feld - so muss das sein! 🏐",
                ],
            },
            WeatherState.MILD_RAIN: {
                PresenceLevel.EMPTY: [
                    "Leichter Regen - der Sand ist frisch und das Feld frei! 🌦️",
                    "Nieselregen hält Mutige nicht auf - das Feld wartet! 🌧️",
                    "Ein bisschen Regen macht den Sand nur saftiger! 🌦️",
                ],
                PresenceLevel.FEW: [
                    "Leichter Regen hält die Hartgesottenen nicht auf! 🌧️",
                    "Kleine Gruppe spielt trotz Nieselregen - Respekt! 🌦️",
                    "Regen? Egal! Ein paar Mutige spielen trotzdem! 💪",
                ],
                PresenceLevel.MANY: [
                    "Voller Einsatz trotz Nieselregen - ihr seid verrückt! 🌧️",
                    "Regen stoppt diese Crew nicht - volles Haus! 🌦️",
                    "Regenvolleyball at its best - echte Fribbe-DNA! 💪",
                ],
            },
            WeatherState.HEAVY_RAIN: {
                PresenceLevel.EMPTY: [
                    "Starkregen - heute lieber trocken bleiben und auf besseres Wetter warten! ⛈️",
                    "Beim Regen ist das Feld frei - aber Vorsicht bei Sturm! 🌧️",
                    "Starker Regen heute - vielleicht besser morgen? ⛈️",
                ],
                PresenceLevel.FEW: [
                    "Starkregen + Volleyball = Legendenstatus! 💪⛈️",
                    "Paar absolut Wahnsinnige spielen trotz Starkregen! 🌧️",
                    "Wer spielt bei diesem Regen? Echte Fribbe-Helden! ⛈️",
                ],
                PresenceLevel.MANY: [
                    "Echte Wikinger! Volles Feld trotz Starkregen! ⛈️",
                    "Starkregen? Die Fribbe-Community schreckt das nicht ab! 💪",
                    "Volles Haus im strömenden Regen - unvergesslich! 🌧️",
                ],
            },
            WeatherState.THUNDERSTORM: {
                PresenceLevel.EMPTY: [
                    "Gewitter - heute bitte drin bleiben! Sicherheit geht vor! ⚡",
                    "Bei Gewitter ist das Feld leer und das ist gut so! ⛈️",
                    "Gewitter zieht auf - bitte warten bis es vorbeizieht! ⚡",
                ],
                PresenceLevel.FEW: [
                    "Gewitter im Anmarsch - bitte Sicherheit beachten! ⚡",
                    "Achtung Gewitter! Spielpause empfohlen! ⛈️",
                    "Bei Blitz und Donner bitte das Feld verlassen! ⚡",
                ],
                PresenceLevel.MANY: [
                    "Gewitter - bitte sofort das Feld verlassen! Sicherheit geht vor! ⚡",
                    "Achtung: Gewitter! Alle vom Feld - Sicherheit zuerst! ⛈️",
                    "Beim Gewitter gilt: Rein ins Trockene! Sicherheit geht vor! ⚡",
                ],
            },
            WeatherState.SNOW: {
                PresenceLevel.EMPTY: [
                    "Schnee auf dem Feld - Wintervolleyball für Mutige! ❄️",
                    "Weißer Sand? Schnee! Das Feld wartet auf Winterhelden! ⛄",
                    "Schneebedecktes Beachfeld - einmalig! Wer traut sich? ❄️",
                ],
                PresenceLevel.FEW: [
                    "Schnee trifft Sand - kleine aber mutige Gruppe! ⛄",
                    "Volleyball im Schnee - das muss man erstmal schaffen! ❄️",
                    "Winter-Wahnsinn! Paar Unerschrockene spielen im Schnee! ⛄",
                ],
                PresenceLevel.MANY: [
                    "Volleyball im Schnee - ihr seid absolute Legenden! ⛄",
                    "Schnee? Egal! Volles Haus und Wintervolleyball! ❄️",
                    "Schneegestöber und volles Feld - das ist Fribbe at its best! ⛄",
                ],
            },
        }

    def get_season(self, last_updated: datetime) -> str:
        """Map a datetime to a season name."""
        month = last_updated.month
        if _SPRING_START <= month <= _SPRING_END:
            return "spring"
        if _SUMMER_START <= month <= _SUMMER_END:
            return "summer"
        if _AUTUMN_START <= month <= _AUTUMN_END:
            return "autumn"
        return "winter"

    def get_daytime(self, last_updated: datetime) -> str:
        """Map a datetime to a time-of-day category."""
        hour = last_updated.hour
        if _MORNING_START <= hour < _MORNING_END:
            return "morning"
        if _DAY_START <= hour < _DAY_END:
            return "day"
        if _EVENING_START <= hour < _EVENING_END:
            return "evening"
        return "night"

    def _pick_message(
        self,
        level: PresenceLevel,
        occupancy: OccupancyType,
        occupancy_time_str: str | None,
        weather: Weather | None = None,
    ) -> str:
        if occupancy == OccupancyType.FULLY:
            formatted_occ_messages = [message.format(ftime=occupancy_time_str) for message in self.occupied_messages]
            return random.choice(formatted_occ_messages)  # noqa: S311

        # 30% chance for a weather-aware message when weather is available
        if weather is not None and random.random() < _WEATHER_MSG_CHANCE:  # noqa: S311
            # Combine any matching weather-state and temperature message pools.
            state_pool = self.weather_state_messages.get(weather.state, {}).get(level)
            temp_pool = self.temperature_messages.get(weather.temperature, {}).get(level)
            weather_message_pool = (state_pool or []) + (temp_pool or [])
            if weather_message_pool:
                # Pick uniformly from the combined pool; odds depend on pool sizes.
                return random.choice(weather_message_pool)  # noqa: S311

        # 20% chance for a combo message
        if random.random() < _COMBO_MSG_CHANCE:  # noqa: S311
            return random.choice(self.combo_messages)  # noqa: S311

        for_datetime = datetime.now(tz=ZoneInfo(env.TZ))

        # 40% chance for seasonal or daytime-dependent messages
        if random.random() < _SEASONAL_MSG_CHANCE:  # noqa: S311
            daytime = self.get_daytime(for_datetime)
            if daytime in self.time_messages and level in self.time_messages[daytime]:
                return random.choice(self.time_messages[daytime][level])  # noqa: S311

            season = self.get_season(for_datetime)
            if season in self.seasonal_messages and level in self.seasonal_messages[season]:
                return random.choice(self.seasonal_messages[season][level])  # noqa: S311

        # Fallback to base messages
        return random.choice(self.base_messages[level])  # noqa: S311

    def get_status_message(
        self,
        level: PresenceLevel,
        occupancy: OccupancyType,
        occupancy_time_str: str | None,
        weather: Weather | None = None,
    ) -> StatusMessage:
        """Return a randomized status message for the current conditions."""
        return StatusMessage(message=self._pick_message(level, occupancy, occupancy_time_str, weather))

    def get_push_message(
        self,
        level: PresenceLevel,
        occupancy: OccupancyType,
        occupancy_time_str: str | None,
        weather: Weather | None = None,
    ) -> PushMessage:
        """Return a randomized push notification message."""
        body = self._pick_message(level, occupancy, occupancy_time_str, weather)
        title_pool = self.push_titles.get(level, self.push_titles[PresenceLevel.FEW])
        title = random.choice(title_pool)  # noqa: S311
        return PushMessage(message=body, title=title)
