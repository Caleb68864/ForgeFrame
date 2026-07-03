---
title: "Composite Fire Into Your Scenes - Kdenlive Tutorial"
video_id: mfF_DEGylqY
url: https://www.youtube.com/watch?v=mfF_DEGylqY
channel: Nuxttux Creative Studio
playlist: kdenlive-tutorials
uploaded: 2024-03-09
duration: 9:03
type: reference
tags: [kdenlive, tutorial, transcript]
---
# Composite Fire Into Your Scenes - Kdenlive Tutorial

## Transcript
[00:10]
hi and welcome to knto creative Studio my name is Jonathan and in this video I'll be showing you how you can easily add fire overlays to your videos and track it to your scene now this video is not sponsored by anyone but if you're looking for some cool assets such as fire smoke rain lightning Etc there are two websites that I can recommend where you can find some free and paid assets you have FX elements and you have action VFX all right I'll start by adding the clips to the timeline I created a zone for this clip since the first frame is a black solid by clicking on the film icon I can import just the video next I'll add the fire overlay I added two effects of the fire directly inside the project bin levels and rotoscoping it might be

[00:55]
difficult to see but the black solid around the flame isn't completely black this could cause issues later on using levels I can increase the input Black Level to fix that next we have the rotoscoping that I use to exclude the parts of the flame I don't want such as the small flame at the bottom I have the alpha operation set to minimum I'll use the film icon to only import the video that I'll place above the first clip and trim it down I'll click the purple dot in the bottom left corner of the top clip to add a transition the transition will match the overlapping areas of our two clips and the effects and composition stack I'll switch from wipe to composite and transform and set compositing to screen I'll use the

[01:40]
composite and transform to position scale and rotate the flame but first I'll add a horizontal flip to the fire clip then I'll position the flame on the door now if we play back or scene the Fire doesn't stick to the door obviously I'll disable the fire track and select the first clip in effects I'll search for motion tracker and add it to the clip we'll get a red rectangle that we can scale and reposition or look for something to track in the scene something static will work best in this case zoom in for a better view there are few tracker algorithm options to choose from dasam and Nano or AI powered and you have to download some libraries to use them the links to the libraries are available in

[02:25]
the Kaden live online documentation I'll stick with KCF for this one you can adjust the key frame spacing depending on your footage use smaller numbers for shaky footage I'll then click on analyze to apply effect and K alive will start tracking if we play back we can see the result we can zoom in to see if anything is off the track is a little shaky but I'll fix that later for now I'll copy the key frames then disable the tracker don't delete it I'll then import the key frames you copied to the fire or rather to the composite and transform layer click on on the hurger menu and select import key frames from clipboard data to import is rectangle set map to position set to Center and

[03:10]
Center uncheck limit key frame number now I'll use the position offset to fix the position of the fire I'll scroll up and down hold control or command for higher increments so up down left right then click okay when when I play back we can see that the fire sticks to the door but moves out of place this is less about the tracking and more about the perspective change I think fix this or add a transform to the fire clip and manually correct the position and scale of the flame as the camera moves closer the objects look bigger now to blend the flame into the scene or add a saturation effect and lower the saturation of the fire then I'll add a lift gamma gain to

[03:57]
tweak the values and colors of the fire fire you can also change the color of the fire Al together next I'll add a gan blur and set the X and Y to three now to fix the shaky tracking I'll disable the effects on the fire clip select the first clip turn on the tracker hit reset and proceed to tracking something else in the scene you can automatically remove all key frames after cursor using the hamburger menu next I'll repeat what I did before copying the key frames and importing them into the composite and transform layer I'll reenable the effects on the fire clip now when I play back it's less jittery next I'll add smoke behind the fire I'll select the fire clip in the composite layer and

[04:42]
move them to the track above notice that her fire overlay broke to fix this I'll select the composite layer and change composite track from automatic to V1 since that's where our first clip is on track V1 now to add smoke over in the project bin I have the smoke AET to which I added a rotoscoping set to substract with some fettering I'll drag it onto the timeline match the length of the other clips and proceed to adding the composition layer switch it to composite and transform but this time I'll set it to multiply since the background is a white solid I'll use the composite layer to position scale and rotate the smoke add a rotoscoping effect to the Smoke to mask out the top

[05:27]
that's being cut by the edge of the frame you'll notice that the mask is behaving out of place that is because it's affecting the original position of the smoke and not the transform result that we're getting from the composite layer to fix this move the composite layer out of the way and adjust the mask next we can move the composite layer back into place make sure to set the rotoscoping to minimum so that it takes into account the rotoscoping from the project bin with the smoke in position I'll import the key frames from earlier into the compon deposite layer of the smoke same as we did with the fire next I'll drag and drop the corrective transform of the fire onto the smoke the smoke is a little low in the frame I'll add another transform to

[06:13]
move it up a little next I'll add a curves set the channel to Alpha to control the opacity of the smoke and rotoscoping I'll then add a lift gamma gain to add some red to the smoke so it looks like the fire is is interacting with it now to make it look like the fire is part of the scene I'll select the first clip and add a rotoscoping mask and mask apply make sure it's rotoscoping mask and not just rotoscoping in between those two I'll add a colorize an EDG glow and a dart effect set the colorize U to match the color of the fire adjust brightness and saturation then for Edge glow use a low threshold Cod bump up the

[07:01]
brightness and set down scaling to a minimum I'll animate the start starting with a 7 amplitude and 80 frequency jump to the end add a key frame set amplitude to 15 and frequency to 120 now for the rotoscoping mask go to the first key frame I'll draw a mask around the fire grabbing the areas that will be affected the most by the flame I'll scrub through and key frame the mask add fettering then I'll play back everything smoke tends to move faster than what I have here but if we adjust the speed of the smoke while we have an effect with key frames like the transform we added to the smoke earlier the key frames will

[07:47]
get lost in translation fortunately the corrective transform came from the fire clip so we can easily get it back I'll hold down control or command left click on the edge of the smoke clip in and drag it in this will change the speed as indicated by the percentage number on the left of the clip then I'll drag it back out without holding control or command notice that the transform key frames are displaced I'll delete that transform effect go to the fire clip and drag the corrective transform back onto the smoke then I'll move it up the stack and we're done this is what we started with and this is what we have now feel free to build upon this and modif these settings and really adapt this to your scenes you don't have to

[08:33]
follow what I do word for word obviously what you'll be working on is different than what I'm working on all right and that's it for this video if you liked it feel free to give it a thumbs up if you didn't like it there is a thumbs down option but who clicks on that seriously though if you have any questions doubt or suggestions feel free to leave them in the comment section down below and I'll get back to you this is nuck creative Studio my name is Jonathan and I'll see you next time
