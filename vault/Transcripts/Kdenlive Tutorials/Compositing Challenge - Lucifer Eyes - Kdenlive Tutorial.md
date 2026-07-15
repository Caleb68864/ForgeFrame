---
title: "Compositing Challenge: Lucifer Eyes - Kdenlive Tutorial"
video_id: S8-GYX2AYnM
url: https://www.youtube.com/watch?v=S8-GYX2AYnM
channel: Nuxttux Creative Studio
playlist: kdenlive-tutorials
uploaded: 2025-01-06
duration: 21:38
type: reference
tags: [kdenlive, tutorial, transcript]
---
# Compositing Challenge: Lucifer Eyes - Kdenlive Tutorial

## Transcript
[00:00]
in this video I'll be showing you how I made the Lucifer's eyes effect and breaking down how I made this scene [Music] here all right so we'll start with the eyes this was a request on how to make the Lucifer eye effect from the show Lucifer this is something similarish you could say all right so over here inside of K and live I have the clip on the timeline I already know what's what's expected what we're going to work on on the clip here I have a marker to Mark where the VFX portion of it is supposed to end so we're all set to start with the VFX I'll start by saying that there are several ways of doing this but this is the method that I chose to go with

[00:46]
and I'll also be showing some alternatives on the way so first off we have our first clip what goes inside of the TV and if you look at the top and bottom of the monitor you'll see black bars this is because this clip has a different aspect ratio than that the project it's a 17 by9 and the project is 16 by9 so to fix this we can either add a transform effect and scale it up or use the new built-in transform effect inside of Kaden live which you first have to enable by going inside of settings down to configure Kaden live and over here this check box you have the enable built-in effects check it on click apply okay and then you'll have flip effects and a built-in transform so in my case I'll be using the built-in transform note that the border of the effects will have an impact so go ahead

[01:33]
and enable the transform I can see the borders here thanks to the edit mode so there are several ways to scale this up to fit the canvas the first one is with this first magnifying glass on the right which will allow you to fit the height and then you can Center vertically or you can simply click on this magnifying glass over here which will adjust in Center in frame and it's going to do this right there I did do some transforms to this clip but they won't really affect what we're about to do next so I'm going to start with the rotoscoping of the eye I'll go ahead and zoom in as much as needed I'll start with the eye on the right which is her left eye okay and now I'll add a rotoscoping effect we'll make a selection now for the rotoscoping you

[02:19]
see if I remove the cursor from the project monitor it says click to add points right click or press enter to close shape so being on the very first frame of where the Ros scoping is going to start I'm going to left click once it adds a point left click somewhere else it's going to add another Point left click over here add another Point left click once more I'll add one here and then I'm going to right click to close the selection now this is our selection so in order to see all of our image we can simply change the alpha operation to add for example and now we can see everything set the Fetter WID to one and the Fetter passes to too we'll see what that does in a moment so now when it comes to the rotoscope to add points if

[03:05]
you want to add additional points you simply have to double click on this highlighted blue line so double click on it and it will add a point you can move it around as you can see and to delete a point simply double click on that point and it will delete that point next we have the handles and the handles allow us to curve the path so now we can better fit the shape of the the eye now this is something that requires a bit of patience and I am not a fan of rotoscoping in general and even less in kid and live now once we have our selection we can simply move a few frames forward now in order to move the entire selection simply click on the little X in the middle here and you can

[03:50]
drag it anywhere you want now if we do this notice there's no new key frame so I'm going to control Zed I'm going to add a key frame manually and then I'm going to move this and now technically if I move a few frames forward again and I move the mask it should add a key frame automatically so there we go this is if you have the automatic key frames activated here on the on the right side of the monitor so automatic key frames if not just continue adding key frames manually you can maybe uh restart K in live because that's just a little bug I've seen sometimes where it won't add the key frames automatically so that's basically what we're going to be doing until we reach the end of the VFX

[04:35]
portion so it's move through time see where the I changes Direction key frame was added automatically I'll add a key frame now I'll simply match the eyes closing and then we're done with this eye for the rotoscope now past this point we've already closed the eyes we can simply go back and see if there's anywhere where not synchronize and refine the selection now if ever you get these little dotted outlines and you can see there's no controls here you can either disable and enable the edit mode again or click off the effect and back on it it's again another one of these little bugs I've noticed I will be reporting

[05:23]
all of them as soon as I can ensure that I can reproduce them so that's our first rotoscope next we're going to do a little bit of tracking the tracking will be for the iris itself so let's go ahead and look for motion so motion tracker now add a motion tracker over here we can either you know maybe zoom out a bit to move the motion tracker I'll place it at the corner of the eye or click hold down control and scale it down it's not exactly the middle I think this has to do when zooming in on the project monitor oh chroma key is on I'll have it track the corner of the ey I'll set the key frame spacing to three so every three frames it's going to add a key frame and I'll leave the tracker

[06:08]
algorithm to KCF now for this part in order to avoid having to analyze the entire track which is what K I would do I'm going to create a new track here under this track I'm going to copy this clip paste it underneath and I'm going to trim it down to the VFX section over here as such and now I'll use this clip at the bottom here to analyze starting on the first frame and then analyze to apply effect this way there's less work for Kaden live and the tracking and there we have it so we can see here now there might be some frames where it's offsetted a bit which you can always fix

[06:53]
afterwards so now we have the first motion tracker now you would repeat those same steps with the other eye so with the top clip selected I'll delete this with the top clip selected I'm going to add another rotoscoping and repeat all the same steps so I'm going to rotoscope this I over here zoom in set this to one set this to two on we have the selection we move a few frames forward until there's a change of direction of the movement and we Mark that change with a key frame move the selection move forward a few frames all done with the rotoscoping so

[07:38]
I have a timeline Zone over here so I have a inpoint and an out point and over here we have the preview the preview render I have it set to automatic preview now you can go over to project project settings and see what you have or your settings for the timeline preview in my case I'll leave it to what I have it now and click on it and now it's going to generate a timeline preview so it's going to pre-render this segment here so we can have smooth playback when we're looking at what we're doing here so in the meantime I'm going to grab another motion tracker and I'm going to track the corner for this eye now that we've rotoscoped both eyes and we have both of them tracked we can go ahead and start either changing the

[08:23]
color of the eyes completely or simply adding the iris so to change the color of the eyes you could do it directly ins inside this clip since you already have the rotoscoping you would simply have to do a mask apply sandwich so you look for mask you get a mask apply put it at the bottom here a rotoscoping mask put it above the rotoscoping and then you could add a colorize so that would be colorize added above the mask apply and under the rotos Scopes and now we have to change the modes here so the first one will be minimum and the second one will be add and now you can change the color of the eyes now of course the issue here is this will last beyond the VFX portion so

[09:11]
you would either have to cut the clip up like use this bottom portion here or something of the sort or we can simply use a solid color above and add the rotos Scopes to that which is the method that I went with so I'll show you how to do that I'll delete these effects over here since we won't be using them now we simply have to transfer these Ros Scopes over to the solid color we can do this by simply drag and dropping so I'm going to drag and drop the first one drag and drop the second one and now I can disable these on the video clip and over here in the color if we just cut it right at the end of the VFX it won't be a problem because it's going to disappear at the very last frame you can [Music] say at the moment we simply have a very

[09:58]
harsh solid color over the eyes so we're going to add a composition track switch the well the composition track to Cyro blend and now we can switch the blend mode in my case I'll go with color burn can control the opacity now this is optional of course depends on the effect you're going for and if you want to exclude the iris from this selection you could add a shape uh an alpha shape to the color change the the shape to ellipse the operation to subtract and now you could place it over just the iris to exclude it but then you'd have to manually track this so you would do the

[10:43]
same thing we did with the rotoscope which is just to track it and make sure it follows the iris around and then you'd have to add another one for the other eye so of course that is if you want to exclude the irises all right so now to add the pupils I'm going to insert track I'm going to insert two new tracks press okay and I have this image over here so just an iris I used a coloriz to make it red and now I'll simply drag it onto the timeline and trim it down so now we have our Iris I'm going to use the built-in transforms to change the original size so we'll make it let's say 4.5 still a little too big so it doesn't have to be the exact same size that is up to you you can lower the opacity for

[11:29]
now just to see what's happening underneath so this will be for the size in the position more or less and now I'm going to go grab the tracking the motion track over here for this eye I'm going to go in it go down to the hamburger menu copy all key frames the clipboard I'm also going to disable it and now going back to our pupil I'm going to add a transform effect to it so this transform effect click on the hamburger menu import key frame I'll switch it to position the map make it Center and then Center to the rectangle I'll uncheck limit key frame number and I'll use the offset these offset sliders here to place the pupil where it's supposed to

[12:14]
go I remove the preview Zone because I think it was affecting the the previewing of this effect so once I have this where I want it I can simply press okay now it will import the key frames now we can play back to see how how how well it's tracked but before that I'm simply going to going to copy this clip here move to the track above so grab this track copy move above go to the start and paste it I'm going to reset this transform go down here go to the second motion tracker this will be for this eye I'll copy all the key frames to clipboard I'll disable it go back to the ey I'll disable the second transform with the first transform selected I can now move

[13:01]
the pupo where it's supposed to go or the iris there we go I can now enable the second transform ignore the offset import key frames the clipboard position center Center remove the limit use the sliders to reposition it now you don't necessarily have to use two effects for this two transforms this method me simply gives you the ability to change the scale of the object that is being tracked or that the track is being applied to which means if the iris moves closer to you it's it's going to look bigger right as we're zooming in and the tracker is going to track the position

[13:47]
but not the size so having to transform allows you to change the size of the object that is tracking or the track is being applied to right so now we have these two we can always go ahead and correct the frames so to do that you would grab the transform jump from Key frame to key frame and do some minor Corrections with the X and Y position like this one over here seems to be a little bit too much of a jump okay and then next we would grab the rotos Scopes so we have this rotoscoping here this is for that eye so drop it on this one then we have this Ros scope which is for the other eye and now we just have to enable it and it's going to cut the eye and keep it inside here we see this one is set to add so

[14:33]
we're going to go with minimum there we have it they're both set to minimum we can turn off the edit mode to see how it's looking it seems to spill a little bit on the top here and one way to fix that or regardless would be to use an alpha operations and we can switch it to let's say shrink soft and you can see the effects here how it's shrinking it a bit right this is optional of course I can drag and drop this this on the other one and do the same thing all right okay if you were to add another Alpha operation before the rotoscope it would affect just the iris so you could have two alpha operations in there so we can see this one here the tracking might need some refinement so if I jump all the way to the beginning let's see how

[15:18]
it looks seems pretty centered then it moves a little too low I think too much to the right too much to the right again so I manually did the correction for the these frames you could always try tracking again and see if you get a better track but honestly a little bit of manual correction here is not the worst thing at this point for these now if you wanted to blend the top Iris with the the original ones you could go and add a composition track to each one of these so let me go ahead and collapse these over here doesn't make much of a difference okay and switch switch it to a CYO blend and you can switch the blend mode to whichever one

[16:04]
works for you let's say lighten in this case and we have to switch the composition track to in my case it would be V3 although I might delete this V2 but in the meantime it's V3 so I'm going to set it to B3 over here you can see it's now blending with the eye I'll repeat the same thing for the other one so I'll add a composition track switch it to the chyo blend and switch the blend mode to lighten and switch the subract the V3 and there we have it now this is it for the eyes this is how I did the eyes segment of it I can turn this one off we're not going to be using it uh for this one I'll keep the rotos scoping we have the motion trackers on this so maybe don't delete it or pass the motion trackers onto this main one now how did I modify the background of

[16:50]
this clip over here I first use a chroma key and I removed the red I lowered the I lowered the variant a little bit and and afterwards I used an alpha operations this was to soften the edges so if I zoom in a bit you can see with the edges of the hair there are some errors showing up so I use the blur might reduce it ever so slightly next I added a CMYK adjust I set it to relative and I remove the Reds so you can see how it's clearing out a lot of the Reds and by adding it to the video clip it's not affecting the eyes but the blend mode of course with changing the values beneath it's going to affect what is above with the blend mode next I added a lift gam

[17:36]
again and I used it to let me zoom out a bit here I used it to remove a lot of Reds from the Shadows a little bit of green and I increased a little bit of blue so I introduce a bit of blue into the Shadows then for the gamma I kind of Simply reduce a little bit of brightness and a little bit of red into it and then for the gain which is the highlights I reduce a little bit of red R again and introduce a bit of green you could say bit of greenish bluish green and that's really it that's how I modified this clip and where changes you can see the eyes are a lot more pronounced now you could even add some noise or Texture to the color that you're adding by adding a video noise generator optional and

[18:22]
finally I created a background with a solid color so the original color is more on the green side over on the timeline I added a colorize so I can change the color of it a video noise generator that I have set to uniform noise and this is because the vignette because I also added a vignette the vignette was causing a bit of banning I don't know if you can see it on your monitor in the noise remove that so once I was done with all of this I simply put it all inside of a sequence which is composition one or comp one then I moved over to comp two and inside of comp two over here I let me move away the composition I brought in our comp one over this video of the screen here so

[19:07]
it's a static shot now the scan line I won't be using it but I use the corners effect and the corners effect allows you to deform a clip or image using corners and I have a transform to scale it down so I first added the transform and scaled it down and then I did the corners then I added a rotoscope so I could make it match inside of the screen and finally an alpha operation just to soften these edges now for the scene in the background I have a brightness that I use to lower the intensity now the rotoscope is here cuz I first rotoscoped it on the screen and then I moved it over to this track so the brightness I

[19:52]
use to lower the overall brightness and then a lift gamma gain just to lower the Shadows a little bit more than anything and finally I applied a lot for the final look and then for the for the clip above I use a composition track switched it to CYO blend and set the blend mode to screen and right at the end here for the screen turning off this is a old preset or template that you could find inside of Ken live it's called the shut off so it's shut off and you can find it in older versions of live so I had to download a much older version just to save it and keep it in my own Library so I didn't put all of this inside of its

[20:38]
own comp and I brought everything inside of the sequence one so over here I did the sound design you could say I added a soft glow the soft glow is simply to make the screen have this little bit of a ghostly glow to it you could say and a transform so that it zooms in and gradually zooms back out now over on Master if you know Master affects everything I added a vignette just to darken the surroundings a little bit let me mute this over here all right and a letter box so I added these black bars at the top and bottom and over here would be the perfect spot to preview the timeline all right and that's how I created this Lucifer's eyes effect and

[21:24]
how I made this entire composition if you want to learn more about killing live you can click display this here I also have classes available on skill share and EM me links are in the description and thanks for watching
