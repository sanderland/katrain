# Themes

Version 1.7 brings basic support for themes, and 1.9 extends it to include keyboard shortcuts and support for multiple theme files.

## Creating and editing themes

* Look at the `Theme` class in `katrain/gui/theme.py`.
* Make a `theme<yourthemename>.json` file in your `<home dir>/.katrain` directory and specify any variables from the above class you want to override, e.g. 
 ```json
 {
  "BACKGROUND_COLOR": [1,0,0,1],
  "KEY_STOP_ANALYSIS": "f1"
}
  ```
* All resources (including icons which can not be renamed for now) will be looked up in `<home dir>/.katrain` first, so files with identical names there can be used to override sounds and images.
* If variables are specified in multiple theme files, the *latest* alphabetically takes precedence. That is, each later theme file overwrites the settings from any previous one.

## Installation

* To install a theme, simply unzip the theme.zip to your .katrain folder. 
  * On windows you can find it in C:\Users\you\.katrain and on linux in ~/.katrain.
  * When in doubt, the general settings dialog will also show the location.
* To uninstall a theme, remove theme.json and all relevant images from that folder.

## Available themes

### Alternate board/stones theme by "koast"

[Download](https://github.com/sanderland/katrain/blob/master/themes/koast-theme.zip)

![Preview](https://raw.githubusercontent.com/sanderland/katrain/master/themes/koast.png)

### Lizzie-like theme

* Theme created by Eric W, includes modified board, stones
* Images taken from [Lizzie](https://github.com/featurecat/lizzie/) by featurecat and contributors.
* Hides hints for low visit/uncertain moves instead of showing small dots. 

[Download](https://github.com/sanderland/katrain/blob/master/themes/eric-lizzie-look.zip)

![Preview](https://raw.githubusercontent.com/sanderland/katrain/master/themes/eric-lizzie.png)

