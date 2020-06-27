# Contributing 

If you are a new contributor, please first discuss the change you wish to make via
 an issue, reddit or discord before making a change.

## Python contributions

Python code is formatted using [black](https://github.com/psf/black) with the settings `-l 120`.
This is not enforced, and contributions with incorrect formatting will be accepted, but formatting this way is appreciated.

## Translations

Adding a translation requires making a new `.po` file with entries for that languages.

* Copy the [English .po file](https://github.com/sanderland/katrain/blob/master/katrain/i18n/locales/en/LC_MESSAGES/katrain.po)
* Change all the `msgstr` entries to your target language.
    * Note that anything between `{}` should be left as-is.
    * The information at the top of the file should also not be translated.

You can send me the resulting `.po` file and I will integrate it into the program.
 
For those who have some python experience as well, you can:

* Replicate the directory structure `katrain/i18n/<lang>/LC_MESSAGES/katrain.po`.
* Run `python i18.py` which will generate the `.mo` files and check for any errors.
* Find `gui.kv` and add a button near the others: 
    ```
    LangButton:
        icon: 'img/flaticon/flag-<lang>.png'
        on_press: app.language = '<lang>'
    ```
* The language should now show up in the app.
* Pull request your changes to the latest minor version branch.

# Contributors 

## Primary author and project maintainer:

[Sander Land](https://github.com/sanderland/)

## Contributors

Many thanks to these additional authors:

* Matthew Allred ("Kameone") for design of the v1.1 UI, MacOS installation instructions, and working on promotion and YouTube videos.
* "bale-go" for development and continued work on the 'calibrated rank' AI.
* "Dontbtme" for detailed feedback and early testing of v1.0+.
* "nowoowoo" for a fix to the parser for SGF files with extra line breaks.
* "nimets123" for the timer sound effects.
* "fohristiwhirl" for the Gibo format parsing code.

## Translators

Many thanks to the following contributors for translations.

* French: "Dontbtme" with contributions from "wonderingabout"
* Korean: "isty2e"
* German: "nimets123"
* Spanish: Sergio Villegas ("serpiente") with contributions from the Spanish OGS community
* Russian: Dmitry Ivankov and Alexander Kiselev
* Simplified Chinese: Qing Mu with contributions from "Medwin"

## Additional thanks to

* David Wu ("lightvector") for creating KataGo and providing assistance with making the most of KataGo's amazing capabilities.
* "세븐틴" for including KaTrain in the Baduk Megapack and making explanatory YouTube videos in Korean.

