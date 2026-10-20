"""Starter text for each concern's page (goherbal.health/concerns/...), keyed by concern name.

Placeholder copy written around the seed catalogue: rewrite it once the real products are in,
so each page names the herbs actually on sale. Edit it in the admin (Products -> Symptoms ->
Intro), not here: this file only fills intros that are still blank.

Wording rules (Kenya's Pharmacy and Poisons Board and Consumer Protection Act, and Google's
standards for health pages): say what herbs are *traditionally used for*, never that they
treat, cure or prevent anything, and always say when to see a doctor. Paragraphs are
separated by a blank line; the first sentence becomes the search-result description.
"""

CONCERN_INTROS = {
    "Headache": """Tension headaches, the tight band around the forehead after a long day at a screen, in traffic or short on sleep, are some of the most common aches there are. Water, food, rest and fresh air are always worth trying first.

Peppermint has long been used for everyday tension headaches, usually as a cooling oil rubbed on the temples and the back of the neck. Lavender's scent is often used alongside it to help you unwind. Keep peppermint oil away from the eyes, and don't use it on babies or young children.

See a doctor urgently if a headache is sudden and severe ("the worst ever"), comes with a fever, stiff neck or rash, follows a knock to the head, or brings weakness, confusion, trouble speaking or changes in your vision. Headaches that keep getting worse, or that start for the first time after 50, also need checking.""",
    "Insomnia": """Can't fall asleep, or waking at 3am and lying awake? Most people have spells of poor sleep, often brought on by stress, late screens, caffeine or a changing routine. A regular bedtime, a dark, cool room and no phone in bed help more than anything else.

Chamomile, lemon balm and lavender have been used for generations to wind down in the evening, as a warm cup an hour before bed or a sachet by the pillow. Valerian root is the traditional choice for restless nights. It can make you drowsy, so don't drive afterwards or take it with alcohol or sleeping tablets. Chamomile isn't for anyone allergic to daisy-family plants.

Speak to a doctor if poor sleep lasts more than a few weeks, if someone notices you snore loudly with pauses or gasps in your breathing, or if you also feel low or hopeless most days.""",
    "Stress & Anxiety": """A racing mind, tight chest or knotted stomach are how many of us feel stress, from work, money, exams or family. Movement, daylight, regular meals, enough sleep and talking to someone you trust all make a real difference.

Holy basil (tulsi), chamomile, lemon balm and lavender are traditionally sipped or breathed in to help you slow down, and ashwagandha root is used in Ayurveda for everyday stress. Ashwagandha isn't suitable in pregnancy, and anyone taking thyroid, diabetes, blood-pressure or mental-health medicines should check with a pharmacist or doctor first.

If worry or low mood lasts for weeks, causes panic attacks, or gets in the way of work, sleep or relationships, please talk to a doctor or counsellor. Help works. If you ever think about harming yourself, call 999 or 112, go to the nearest hospital, or call the Kenya Red Cross free on 1199.""",
    "Digestive Issues": """Bloating, indigestion, a heavy stomach after a big meal or an occasional upset tummy usually settle by themselves. Smaller meals, eating slowly, drinking water and moving after you eat often help.

Ginger is the classic warming root for an unsettled stomach and queasiness, and peppermint is traditionally sipped after meals. Licorice root has long been used to soothe the digestive tract, but it isn't for anyone with high blood pressure, heart or kidney problems, or who is pregnant, and shouldn't be taken for long stretches. Ginger in large amounts may not suit people taking blood thinners.

See a doctor if you notice blood in your stool or black stools, vomit blood, have severe or lasting pain, lose weight without trying, or find it hard to swallow. With diarrhoea, drink plenty and use oral rehydration salts (ORS); get help quickly if a child, older person or anyone pregnant shows signs of dehydration.""",
    "Cold & Flu": """A blocked nose, sore throat, cough and aches usually run their course in about a week. Rest, plenty of fluids, warm drinks and steam inhalations are the comfort measures most people reach for.

Echinacea is traditionally taken at the first sign of a cold, and warming ginger, honey and lemon in hot water is a household favourite for a scratchy throat. Echinacea isn't recommended in pregnancy, for people with autoimmune conditions, or alongside medicines that suppress the immune system. Honey isn't safe for babies under one.

In Kenya, any fever should be tested for malaria. Visit a clinic the same day, especially for children, pregnant women and older people. Get medical help straight away for difficulty breathing, chest pain, a fever lasting more than three days, a child who is unusually drowsy or not drinking, or symptoms that last longer than ten days.""",
    "Joint Pain": """Stiff knees after a long day, sore hands in the morning or aches that come with age and hard work are very common. Staying active, gentle stretching, a healthy weight and supportive shoes all take strain off the joints.

Turmeric, the golden root behind so much East African and Indian cooking, has a long tradition of use for everyday aches, often taken with black pepper and a little fat. Warm compresses and massage balms are used to ease stiffness. Turmeric supplements may not suit people taking blood thinners or diabetes medicines, or with gallstones; check with a pharmacist first.

See a doctor urgently if a joint is suddenly hot, red and swollen, especially with a fever, or if you can't put weight on it after an injury. Morning stiffness lasting more than half an hour for weeks, pain that wakes you at night, or swelling in several joints also needs checking.""",
    "Low Energy": """Feeling flat, sluggish or drained is often down to the basics: short sleep, skipped meals, too little water, too much sugar or a stressful stretch. Getting those right is the first step.

Moringa leaf, grown widely across East Africa, is valued as a nutrient-rich green to add to food and drinks. Ashwagandha is traditionally used in Ayurveda when people feel run down. Neither is a substitute for a balanced diet, and ashwagandha isn't suitable in pregnancy or for people on thyroid medicines without medical advice.

If you've felt tired for more than a few weeks, see a doctor. Simple blood tests can check for common causes such as anaemia, thyroid problems or diabetes. Get checked sooner if tiredness comes with weight loss, breathlessness, heavy periods, fevers or low mood.""",
    "Skin Irritation": """Dry patches, mild redness, heat rash, insect bites and the odd breakout are everyday skin complaints. Gentle soap, lukewarm water, loose cotton clothing and a good moisturiser go a long way.

Aloe vera gel has been used for generations to cool and soothe skin, and neem leaf is traditionally used across Africa and Asia to keep skin clear. Try any new balm on a small patch of skin first and wait a day. Keep neem products on the skin only: don't swallow them, and keep them away from children.

See a doctor if a rash spreads, becomes hot, swollen or painful, oozes pus, or comes with a fever, as these can be signs of infection. Get emergency help if a rash comes with swelling of the lips, face or tongue or difficulty breathing. Rashes that don't improve within a week or two should also be checked.""",
    "Immune Support": """Good sleep, a varied diet with plenty of fruit and vegetables, regular movement and clean water are the foundations of staying well through the seasons. Herbs are traditionally used alongside these, not instead of them.

Echinacea is the best-known herb for the cold season, and moringa and turmeric are valued as everyday foods across East Africa and beyond. Echinacea isn't recommended in pregnancy, for people with autoimmune conditions, HIV or a transplant, or alongside medicines that affect the immune system, unless a doctor agrees.

Herbs don't replace vaccinations, mosquito nets or prescribed treatment. See a doctor if you seem to catch one infection after another, if infections are severe or slow to clear, or if you have a fever. In Kenya, get any fever tested for malaria.""",
    "Menstrual Discomfort": """Cramps, bloating, tiredness and mood changes around your period are common. Warmth on the lower belly, gentle movement, rest and staying hydrated are what many people find helps most.

Hibiscus, ginger and chamomile teas are traditionally sipped through the cycle for comfort. Hibiscus may lower blood pressure, so it isn't for anyone already on blood-pressure medicines, and hibiscus and other herbal remedies should be avoided if you might be pregnant or are breastfeeding unless a doctor says otherwise.

See a doctor if you soak through a pad or tampon every hour or two, if periods last more than seven days, or if pain isn't eased by usual painkillers or stops you from daily life. Bleeding between periods or after sex also needs checking. Get emergency help for severe pain on one side with a missed period, as it can be a sign of an ectopic pregnancy.""",
}
