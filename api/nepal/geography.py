"""7 provinces / 77 districts with English + Nepali names and common spellings.

Municipalities (753) are not mapped; the district/province in the notice text is what we resolve.
"""

import re
import unicodedata
from typing import NamedTuple

from nepal.numbers import to_ascii_digits
from schemas.enums import Province

# province -> (Nepali name, "English,Nepali;...")
_DATA = {
    Province.KOSHI: ("कोशी", "Bhojpur,भोजपुर;Dhankuta,धनकुटा;Ilam,इलाम;Jhapa,झापा;Khotang,खोटाङ;Morang,मोरङ;Okhaldhunga,ओखलढुङ्गा;Panchthar,पाँचथर;Sankhuwasabha,संखुवासभा;Solukhumbu,सोलुखुम्बु;Sunsari,सुनसरी;Taplejung,ताप्लेजुङ;Terhathum,तेह्रथुम;Udayapur,उदयपुर"),
    Province.MADHESH: ("मधेश", "Parsa,पर्सा;Bara,बारा;Rautahat,रौतहट;Sarlahi,सर्लाही;Dhanusha,धनुषा;Siraha,सिराहा;Mahottari,महोत्तरी;Saptari,सप्तरी"),
    Province.BAGMATI: ("बागमती", "Sindhuli,सिन्धुली;Ramechhap,रामेछाप;Dolakha,दोलखा;Bhaktapur,भक्तपुर;Dhading,धादिङ;Kathmandu,काठमाडौं;Kavrepalanchok,काभ्रेपलाञ्चोक;Lalitpur,ललितपुर;Nuwakot,नुवाकोट;Rasuwa,रसुवा;Sindhupalchok,सिन्धुपाल्चोक;Chitwan,चितवन;Makwanpur,मकवानपुर"),
    Province.GANDAKI: ("गण्डकी", "Baglung,बाग्लुङ;Gorkha,गोरखा;Kaski,कास्की;Lamjung,लमजुङ;Manang,मनाङ;Mustang,मुस्ताङ;Myagdi,म्याग्दी;Nawalpur,नवलपुर;Parbat,पर्वत;Syangja,स्याङ्जा;Tanahun,तनहुँ"),
    Province.LUMBINI: ("लुम्बिनी", "Kapilvastu,कपिलवस्तु;Parasi,परासी;Rupandehi,रुपन्देही;Arghakhanchi,अर्घाखाँची;Gulmi,गुल्मी;Palpa,पाल्पा;Dang,दाङ;Pyuthan,प्युठान;Rolpa,रोल्पा;Rukum East,रुकुम पूर्व;Banke,बाँके;Bardiya,बर्दिया"),
    Province.KARNALI: ("कर्णाली", "Rukum West,रुकुम पश्चिम;Salyan,सल्यान;Dolpa,डोल्पा;Humla,हुम्ला;Jumla,जुम्ला;Kalikot,कालिकोट;Mugu,मुगु;Surkhet,सुर्खेत;Dailekh,दैलेख;Jajarkot,जाजरकोट"),
    Province.SUDURPASHCHIM: ("सुदूरपश्चिम", "Kailali,कैलाली;Achham,अछाम;Doti,डोटी;Bajhang,बझाङ;Bajura,बाजुरा;Kanchanpur,कञ्चनपुर;Dadeldhura,डडेल्धुरा;Baitadi,बैतडी;Darchula,दार्चुला"),
}

_SPELLINGS = {  # canonical -> common alternates
    "Kavrepalanchok": "kavre,kabhrepalanchok,kavrepalanchowk,kabhre,काभ्रे",
    "Sindhupalchok": "sindhupalchowk,sindhupalchock",
    "Chitwan": "chitawan,chitvan",
    "Dhanusha": "dhanusa",
    "Terhathum": "tehrathum,terathum,tehrathum",
    "Makwanpur": "makawanpur",
    "Kapilvastu": "kapilbastu",
    "Bardiya": "bardia",
    "Syangja": "syanja,shyangja",
    "Tanahun": "tanahu,tanahun",
    "Sankhuwasabha": "sankhuwasava,sankhuwasabha",
    "Kathmandu": "काठमाण्डौ,ktm",
    "Okhaldhunga": "okhaldhunga,okhaldunga",
    "Kanchanpur": "kanchenpur",
    "Rukum East": "eastern rukum,rukum purba,east rukum",
    "Rukum West": "western rukum,rukum paschim,west rukum",
    "Nawalpur": "nawalparasi east,nawalparasi purba,नवलपरासी पूर्व",
    "Parasi": "nawalparasi west,nawalparasi paschim,नवलपरासी पश्चिम",
}
_AMBIGUOUS = {"rukum": ("Rukum East", "Rukum West"), "रुकुम": ("Rukum East", "Rukum West"),
              "nawalparasi": ("Nawalpur", "Parasi"), "नवलपरासी": ("Nawalpur", "Parasi")}
_PROVINCE_SPELLINGS = {
    Province.KOSHI: "kosi,कोसी", Province.MADHESH: "madhes,मधेस",
    Province.BAGMATI: "", Province.GANDAKI: "", Province.LUMBINI: "", Province.KARNALI: "",
    Province.SUDURPASHCHIM: "sudurpaschim,sudur paschim,sudur pashchim,far western,सुदुरपश्चिम",
}


class Location(NamedTuple):
    province: Province | None
    district: str | None
    candidates: tuple[str, ...]  # set when the text names several districts or an ambiguous one (Rukum, Nawalparasi)


def _key(s: str) -> str:
    s = to_ascii_digits(unicodedata.normalize("NFC", s)).casefold()
    return re.sub(r"[^\w\u0900-\u0963\u0966-\u097f]+", " ", s).strip()


DISTRICTS: dict[str, tuple[str, Province]] = {}  # English -> (Nepali, province)
PROVINCES_NE: dict[Province, str] = {}
_LOOKUP: dict[str, tuple] = {}

for _prov, (_pne, _rows) in _DATA.items():
    PROVINCES_NE[_prov] = _pne
    for _row in _rows.split(";"):
        _en, _ne = _row.split(",")
        DISTRICTS[_en] = (_ne, _prov)
        _LOOKUP[_key(_en)] = _LOOKUP[_key(_ne)] = ("d", _en)
for _en, _alts in _SPELLINGS.items():
    for _a in _alts.split(","):
        _LOOKUP[_key(_a)] = ("d", _en)
for _i, (_prov, (_pne, _)) in enumerate(_DATA.items(), 1):
    for _a in [_prov.value, _pne, f"province no {_i}", f"province {_i}", f"प्रदेश नं {_i}", *_PROVINCE_SPELLINGS[_prov].split(",")]:
        if _a:
            _LOOKUP[_key(_a)] = ("p", _prov)
for _a, _names in _AMBIGUOUS.items():
    _LOOKUP[_key(_a)] = ("a", _names)

assert len(DISTRICTS) == 77 and len(_DATA) == 7


def _match(toks: list[str], i: int):
    for n in (3, 2, 1):  # longest alias first
        if hit := _LOOKUP.get(" ".join(toks[i:i + n])):
            return n, hit
    return None


def normalize_location(text: str) -> Location:
    """Free text -> (province, district). A district beats a conflicting province mention."""
    toks, i, ds, ps, amb = _key(text).split(), 0, [], [], ()
    while i < len(toks):
        found = _match(toks, i)
        if found is None:
            i += 1
            continue
        n, (kind, val) = found
        i += n
        if kind == "d" and val not in ds:
            ds.append(val)
        elif kind == "p":
            ps.append(val)
        elif kind == "a":
            amb = val
    if len(ds) == 1:
        return Location(DISTRICTS[ds[0]][1], ds[0], ())
    cands = tuple(ds) or amb
    provs = {DISTRICTS[d][1] for d in cands} or set(ps)
    if not cands and len(set(ps)) != 1:
        return Location(None, None, ())
    if len(provs) != 1:
        provs = set(ps) if len(set(ps)) == 1 else set()
    return Location(next(iter(provs), None), None, cands)