"""Random display names for anonymous sessions (z. B. „Funny Rabbit Wizard")."""
import random

# ponytail: display_name ist ein Anzeigename, keine ID — keine globale
# Eindeutigkeit erzwingen (ein used-Set würde pro Erstbesuch die ganze
# User-Tabelle laden). Kollisionen sind harmlos.
_ADJ = ["Funny", "Clever", "Brave", "Sleepy", "Golden", "Sneaky", "Curious",
        "Witty", "Lucky", "Gentle"]
_NOUN = ["Rabbit", "Fox", "Wizard", "Otter", "Panda", "Badger", "Llama",
         "Dragon", "Owl", "Hedgehog"]
_TRAIT = ["Rider", "Keeper", "Hunter", "Dreamer", "Captain", "Ninja",
          "Explorer", "Sailor", "Poet", "Chef"]


def generate_name() -> str:
    return f"{random.choice(_ADJ)} {random.choice(_NOUN)} {random.choice(_TRAIT)}"
