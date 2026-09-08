"""Static city data kept separate from UI helpers."""
IRAN_CITIES = [
    "تهران", "مشهد", "اصفهان", "شیراز", "تبریز", "قم", "کرج", "اهواز", "کرمانشاه",
    "ارومیه", "رشت", "کرمان", "یزد", "همدان", "اردبیل", "زاهدان", "بندرعباس", "ساری",
    "قزوین", "خرم‌آباد", "سنندج", "بوشهر", "اراک", "زنجان", "گرگان", "سمنان", "بجنورد",
    "ایلام", "یاسوج", "بیرجند", "ساوه",
]
IRAQ_CITIES = ["نجف", "کربلا", "کاظمین", "سامرا", "بغداد"]
CITY_COUNTRY = {city: "Iran" for city in IRAN_CITIES}
CITY_COUNTRY.update({city: "Iraq" for city in IRAQ_CITIES})
ALL_CITIES = set(IRAN_CITIES) | set(IRAQ_CITIES)
