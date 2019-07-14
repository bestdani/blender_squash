# Blender Squash

## A game for blender 2.8
Blender squash is a little game rendered using the [blender](https://blender.org) version 2.8 real time viewport (Eevee).
All physics are managed by the python script, the blender viewport is used for displaying the results and playing back some animations.

## A simple gameplay
After having either accepted running the script on starupt of the .blend file or executed the script file, you can control a racket using the arrow key on your keyboard.
Blender squash is over once the ball got spawned and exited the play are without having made any score.
Use the ESC key to properly shut down the game which ensures all temporarily files also get cleaned up.

## A learning project
The main intention for me to create this was getting more familiar with blender's Python API while having already quite a lot of experience using it for 3d modeling and rendering.

## All in one
All resources haven been packed into the single .blend file, but the game python source code is also present in this repository for convenience.
To be able to use the in blender included [audaspace](https://github.com/audaspace/audaspace) python bindings the sound files get extracted using Python's [tempfile](https://docs.python.org/3/library/tempfile.html) library.

## A last hint
Start blender first and toggle the full screen mode or launch it with the -W run option to experience it without any window frame.