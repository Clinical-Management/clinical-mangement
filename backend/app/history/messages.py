"""Fixed patient-facing messages. These never come from the model.
NOTE: Hindi and Marathi wording should be reviewed by native-speaking staff."""

GREETING_AUTO = (
    "Hello! I'm the clinic assistant. I'll ask a few questions so the doctor is ready for you. "
    "You can speak in English, Hindi or Marathi.\n"
    "नमस्ते! आप हिंदी में भी बोल सकते हैं।\n"
    "नमस्कार! तुम्ही मराठीतही बोलू शकता.\n"
    "What is the main problem that brings you in today?"
)

GREETING = {
    "en": "Hello! I'm the clinic assistant. I'll ask a few questions so the doctor is ready for you. "
    "What is the main problem that brings you in today?",
    "hi": "नमस्ते! मैं क्लिनिक की सहायक हूँ। डॉक्टर की तैयारी के लिए मैं कुछ सवाल पूछूँगी। "
    "आज आप किस मुख्य परेशानी के लिए आए हैं?",
    "mr": "नमस्कार! मी क्लिनिकची सहाय्यक आहे. डॉक्टरांच्या तयारीसाठी मी काही प्रश्न विचारेन. "
    "आज तुम्ही कोणत्या मुख्य त्रासासाठी आला आहात?",
}

GREETING_RETURNING = {
    "en": "Welcome back! I'll quickly confirm what we have on record and ask what has changed. "
    "What brings you in today?",
    "hi": "फिर से स्वागत है! मैं आपकी पिछली जानकारी जल्दी से पक्की करूँगी और पूछूँगी कि क्या बदला है। "
    "आज आप किस परेशानी के लिए आए हैं?",
    "mr": "पुन्हा स्वागत आहे! मी तुमची मागील माहिती पटकन तपासेन आणि काय बदलले ते विचारेन. "
    "आज तुम्ही कशासाठी आला आहात?",
}

URGENT = {
    "en": "What you describe may need urgent care. Please tell the front desk right now, or go to the nearest "
    "emergency department. If it is severe, call 108 for an ambulance. The clinic staff have been alerted.",
    "hi": "आप जो बता रहे हैं उसके लिए तुरंत इलाज की ज़रूरत हो सकती है। कृपया अभी रिसेप्शन पर बताएं या नज़दीकी "
    "इमरजेंसी में जाएं। हालत गंभीर हो तो एम्बुलेंस के लिए 108 पर कॉल करें। क्लिनिक स्टाफ को सूचना दे दी गई है।",
    "mr": "तुम्ही सांगत असलेल्या लक्षणांसाठी तातडीच्या उपचारांची गरज असू शकते. कृपया आत्ताच रिसेप्शनला सांगा "
    "किंवा जवळच्या आपत्कालीन विभागात जा. त्रास गंभीर असल्यास रुग्णवाहिकेसाठी 108 वर कॉल करा. "
    "क्लिनिक कर्मचाऱ्यांना कळवले आहे.",
}

NO_ADVICE = {
    "en": "I can't give medical advice, but the doctor will discuss this with you. "
    "Is there anything else about how you feel that the doctor should know?",
    "hi": "मैं दवा या इलाज की सलाह नहीं दे सकती, डॉक्टर आपसे इस बारे में बात करेंगे। "
    "क्या आपकी तबीयत के बारे में कुछ और है जो डॉक्टर को पता होना चाहिए?",
    "mr": "मी औषध किंवा उपचारांचा सल्ला देऊ शकत नाही, डॉक्टर तुमच्याशी याबद्दल बोलतील. "
    "तुमच्या तब्येतीबद्दल डॉक्टरांना आणखी काही सांगायचे आहे का?",
}

REVIEW_READY = {
    "en": "Thank you. Please check the summary below. Tap 'Looks right' to send it to the doctor, "
    "or tell me what to correct.",
    "hi": "धन्यवाद। कृपया नीचे दिया सारांश देखें। सही हो तो 'सही है' दबाएं, या बताएं कि क्या बदलना है।",
    "mr": "धन्यवाद. कृपया खालील सारांश तपासा. बरोबर असल्यास 'बरोबर आहे' दाबा, किंवा काय दुरुस्त करायचे ते सांगा.",
}
