# Themes
Version 1.7 brings basic support for themes.

## Creating and editing themes

* Look at the `Theme` class in `katrain/gui/theme.py`.
* Make a `theme.json` file in your `<home dir>/.katrain` directory and specify any variables from the above class you want to override, e.g. 
 ```json
 {
  "BACKGROUND_COLOR": [1,0,0,1]
}
  ```
* All resources (including icons which can not be renamed for now) will be looked up in `<home dir>/.katrain` first, so files with identical names there can be used to override sounds and images.

## Available themes

* See [https://github.com/sanderland/katrain/blob/master/themes/](here) for available themes. 
* To install a theme, simply unzip the theme.zip to your .katrain folder. 
  * On windows you can find it in C:\Users\you\.katrain and on linux in ~/.katrain.
  * When in doubt, the general settings dialog will also show the location.
* To uninstall a theme, remove theme.json and all relevant images from that folder.

