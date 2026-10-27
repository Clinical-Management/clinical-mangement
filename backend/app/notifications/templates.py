"""Patient message templates in English, Hindi and Marathi.

Keep them short (SMS) and free of clinical advice. The Hindi and Marathi wording should be reviewed by
native speakers before go-live; WhatsApp Business also needs each template approved by Meta."""

from datetime import date

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}

TEMPLATES = {
    "reminder": {
        "en": "{clinic}: Reminder for {patient} - appointment with {doctor} on {date} at {time}. Confirm: {confirm_link} Change or cancel: {manage_link}",
        "hi": "{clinic}: {patient} के लिए याद दिलाना - {doctor} के साथ {date} को {time} बजे अपॉइंटमेंट है। पुष्टि करें: {confirm_link} बदलें या रद्द करें: {manage_link}",
        "mr": "{clinic}: {patient} साठी आठवण - {doctor} यांच्यासोबत {date} रोजी {time} वाजता भेट आहे. निश्चित करा: {confirm_link} बदला किंवा रद्द करा: {manage_link}",
    },
    "follow_up_booked": {
        "en": "{clinic}: A follow-up for {patient} with {doctor} is booked on {date} at {time}. Change or cancel: {manage_link}",
        "hi": "{clinic}: {patient} का {doctor} के साथ फ़ॉलो-अप {date} को {time} बजे बुक है। बदलें या रद्द करें: {manage_link}",
        "mr": "{clinic}: {patient} यांची {doctor} यांच्यासोबत फॉलो-अप भेट {date} रोजी {time} वाजता बुक आहे. बदला किंवा रद्द करा: {manage_link}",
    },
    "follow_up_nudge": {
        "en": "{clinic}: {doctor} advised a follow-up for {patient} around {date}. Please book a visit: {book_link} or call {phone}.",
        "hi": "{clinic}: {doctor} ने {patient} के लिए लगभग {date} को फ़ॉलो-अप की सलाह दी थी। कृपया अपॉइंटमेंट बुक करें: {book_link} या {phone} पर कॉल करें।",
        "mr": "{clinic}: {doctor} यांनी {patient} यांना सुमारे {date} रोजी फॉलो-अपचा सल्ला दिला होता. कृपया भेट बुक करा: {book_link} किंवा {phone} वर कॉल करा.",
    },
    "medicine": {
        "en": "{clinic}: Time for {patient}'s medicines: {medicines}. Take as prescribed.",
        "hi": "{clinic}: {patient} की दवा का समय: {medicines}। डॉक्टर के बताए अनुसार लें।",
        "mr": "{clinic}: {patient} यांच्या औषधांची वेळ: {medicines}. डॉक्टरांनी सांगितल्याप्रमाणे घ्या.",
    },
    "repeat_test": {
        "en": "{clinic}: Reminder for {patient} - repeat tests due today: {tests}.",
        "hi": "{clinic}: {patient} के लिए याद दिलाना - आज दोबारा जाँच करानी है: {tests}।",
        "mr": "{clinic}: {patient} साठी आठवण - आज पुन्हा तपासण्या करायच्या आहेत: {tests}.",
    },
}

SUBJECTS = {
    "reminder": "Appointment reminder",
    "follow_up_booked": "Your follow-up appointment",
    "follow_up_nudge": "Time to book your follow-up",
    "medicine": "Medicine reminder",
    "repeat_test": "Repeat test reminder",
}


def fmt_date(value: str | date, lang: str) -> str:
    d = date.fromisoformat(str(value)[:10]) if not isinstance(value, date) else value
    return f"{d.day} {MONTHS.get(lang, MONTHS['en'])[d.month - 1]} {d.year}"


def fmt_time(hhmm: str | None) -> str:
    if not hhmm:
        return ""
    h, m = map(int, hhmm.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def render(kind: str, lang: str, **values) -> str:
    template = TEMPLATES[kind].get(lang) or TEMPLATES[kind]["en"]
    return template.format(**values)
