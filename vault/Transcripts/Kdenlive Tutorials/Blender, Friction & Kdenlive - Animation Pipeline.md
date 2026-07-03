---
title: "Blender, Friction & Kdenlive - Animation Pipeline"
video_id: 6UePY9iSLCU
url: https://www.youtube.com/watch?v=6UePY9iSLCU
channel: Nuxttux Creative Studio
playlist: kdenlive-tutorials
uploaded: 2025-10-20
duration: 22:13
type: reference
tags: [kdenlive, tutorial, transcript]
---
# Blender, Friction & Kdenlive - Animation Pipeline

## Transcript
[00:00]
Let's break down how you can recreate a video such as this one using open source software such as friction kaden live and blender. Now this was a request made by one of you la aada I hope I'm saying it right who asked if we could recreate this inside of friction. Now a quick disclaimer this is not an in-depth tutorial of either friction kalin live nor blender. We're going to have a brief overview and I'll break down how I went about recreating my version of it. The first thing I did was well watch the reference. Second thing I did was go over to pixels where I looked for some stock footage that I could use. Mainly when you see in the intro of the video, there is a sort of light leak happening inside of the text. Now I could create this procedurally or I could simply look

[00:47]
for a video of a similar light leak and overlay that on the text, which is what I did. So I went to pixels and I looked for a couple light leaks. So I I got five of them here. So you can see this is one of them. So you can see I got various options and then chose one of them to work with. I also got some night skies. So over here I have this first one, but there's a house in the way. Although it does go behind some clouds which would fit nicely with the original or the source. But finally, I settled on this one, which although a bit slow is not really a problem because you can accelerate those clips in friction later on. I also got this one over here, which I didn't use, but it would have been quite fitting with the light show behind

[01:33]
the clouds. So, the first step was to get a few stock videos, so assets to be used when creating this uh this intro, you could say. After that, I jumped into Friction to put everything together and start compositing. So over in friction, if I were to turn off all the layers in order of creation. So here we go. The first one is the coming soon text. And this here is a layer. Now I haven't yet touched on um friction overall. So the UI and the general principles of it, but I'll try to explain this one as simply as possible. this over here. If I right click and I go inside of actions, you can see I have the option to demote to a

[02:18]
group. So there's a difference between layers in group inside of friction. Think of groups for those of you who use Kaden Live. You can think of a group as grabbing multiple clips on the timeline and hitting CtrlG to group them. That's a group. Now, of course, in here, it does go inside of a folder. So, if you've used or Photoshop, you're putting all of these uh clips or assets, objects, etc. inside of a folder. So, it's a group. Now, a layer would be the equivalent of a sequence that you bring onto the timeline. So, it's a more compact group or a more flattened group, you could say. So, the same way that if I created a new sequence and I did a bunch of composite and effects and cuts

[03:04]
and all of that inside of the sequence and then I imported that sequence, it's a flat clip. So, it's a flattened version of everything that we did inside of that sequences timeline. So, that's essentially what a layer is versus a group inside of friction. So, here I'm using a layer because it helps contain the blend modes. Inside of that layer, I have a text object. So, if I turn off these two ones above, I have a text object in here. And inside of that text object, I added text effect. So, if I grab the what's it called here? Point mode. So, this over here is how you control the text effect. Let me scale this up here. Scale this up. So the text

[03:50]
effect I use was inside of transform and it has to do with the opacity. So the opacity is set to zero and if I scrub back and forth you can see how it goes from zero opacity and fades in to full opacity. Okay. Then I use a raster effect. And in the previous video I mentioned that you had things such as shaders which you can think of as plugins or add-ons. And that's one of them. And this effect here is what gives it this disappearing. The way that it's disappearing. And you have different options for making it disappear. Uh I have a couple noise shaders as well that could be used to do that. So there are multiple

[04:37]
options, but I went with this noise fade. Now you might notice that it has a bit of a glow to it. And this is a raster effect that is applied to the layer itself. So it applies to everything inside of the layer. If I turn it off and see and this is simply a shadow using the shadow as a form of a glow. Now above this layer I added one of the overlays. So the light leaks or light shows this over here. And this here is the visibility range instead of the strip that you see here. And now above it, I added a link version of the text. Meaning, whatever happens to this text object is going to reflect on this text object above. That way, I could use

[05:24]
the link object as a mask for the light show and set the light show to hard light. So if I turn on the mask, the mask contains the light show in the text and then the light show is playing as a hard light on the text layer underneath. So I put all of this inside of a layer. This would be the equivalent of a composition or a pre-MP in the context of After Effects. So after the text, I then created the cloudy background. Now this was procedurally created inside of Friction using a shader. So this here that you see is actually just a solid shape with a shader applied to it. So the raster effect is clouds. There's a wide range of shaders available for

[06:11]
download on GitHub. I'll add a link down in the description. I've also made a few custom shaders and modified some of the existing ones. Uh they're also available on GitHub, but they're really just in testing right now. So, so I won't put a link for those, but soon enough I will. As for how to install the shaders, it's really just dragging it into Friction's shader folder. So now, depending on your operating system, that's going to be in a different location. But once I get into a dedicated Friction video, I will go over all of these steps, especially um once the RC3 or version one comes out, just to make sure that the information is up to date. So, jumping back into friction. If I turn off the

[06:56]
clouds shader, you can see how this is just a solid gray rectangle. Let me actually show the outside here because you can crop everything to the canvas. There you go. And so, I took the cloud and I changed the color, make it a bit more purple. I played around with the values to get the shape and look that I wanted. And that's pretty much it. So, this one is just procedurally made. You could also go ahead and grab stock footage of clouds or even images depending on what you have available or the style that you're going for and use that instead. Now, you might also notice that for the cloud over here, I have this blue strip. Now, this blue strip is actually optional and

[07:42]
it's by right-clicking and you have visibility range. This allows you to use the object like a clip with a fixed length. So in other words, if I don't want this shape to be visible from the very first frame, I simply activate the visibility range. And then now I can simply crop it out. So it only appears at this point over here. And that's all it's doing really. I then duplicated the cloud. So this is cloud zero above. So action duplicate. And this cloud above here is simply for the transition. So it's a little introduction. So it fades in and out. You go here, transform. We have the opacity. So it goes from zero opacity up

[08:27]
to I think 55 and then fades out again with a little bit of animation on the animation on the shader itself. So over here the cloud scale. And this is how I introduce the clouds. The ones in the background just appear. And you have the ones in front just slowly appearing first. Now moving on to the lightning. I use the stock footage that I have. Although I'm pretty sure you can create your own lightning. You could even make it inside of another software. You could get stock lightning from Action VFX or a number of other places where you can download assets. I use the stock videos that I got from Pixels. I grabbed the one with the big

[09:13]
lightning strike. I simply renamed the clip so that it would be easier to identify in the in the layers and then I cut it or duplicated it so I would have two layers of lightning happening. So we have this one down here. Now video clips by default normally have the visibility range. So if you import a video clip it's going to have the visibility range by default. And then the other thing that it has is the ability to rightclick, go inside of action, and you have frame remapping. So this allows you to change the speed of your video clips or even imported scenes, but that's a story for another video. So I use this, so the frame remapping in order to

[09:58]
control the speed of the lightning. So I accelerated it at some point because it felt a little too slow. And then I was able to slow it down when necessary and accelerate when necessary. Same thing for this one above here. I'm using the frame mapping to accelerate it and slow it down when the big strike happened, the big flash. So this is basically how I got the lightning in there. Now, finally, we're getting into the 3D text. Now, there is no 3D feature inside of Friction, so I had to jump into Blender to create the 3D text, but it's actually quite simple since it's just plain text moving around. Now, the the one thing that you maybe might want is to have the text uh integrate with

[10:46]
the environment. So, for example, if you had the reflection of the clouds or matching lights or when the lightning strikes, something that reflects that on the text. Now, there are different ways that you can go about that. Uh, one of them would even be to export what we have so far. Bring it into Blender and put it as a HDR background in a way, but I didn't go for all that. I kept it simple. So, let's go ahead and jump inside of Blender and see how the 3D text was made and how we had to use Kaden Live to make it compatible with Friction. So, now we're inside of Blender. I'm going to stick to the normal viewport shading, but you can see that it has the colors and this area around it is actually

[11:34]
metallic, but I'll stick to this right now. I have too many things running on the laptop at the same time. So, in here, I have a sunlight for general lighting. The sunlight is set to a normal color, but it's a bit stronger and the angle is a bit wider, so it covers more area. Then I have this uh area light over here with a bit of a pinkish light quite strong and placed like further above. So all the way up here. And as for the text itself, it was converted into a mesh which is destructive. So if you wanted to change this word, then you'd have to start from scratch. Although I think you could use uh geometry nodes for this, but I'm not very familiar with geometry nodes. Although I'm pretty sure that

[12:20]
geometry nodes would be the way to go to make this procedurally. So inside the camera view here, if I play back, we have our text animation where all it does is come from above, go down into position, and then jump back above. Now, if I jump to animation here, I did play with the curves a little bit just to give it a bit more of an ease in ease out feel. And to create this, well, this, like I said, this is not a full-on tutorial on step-by-step process, but essentially you would press shift A to add. You go down to where is it? Text. Press tab to

[13:05]
get into edit mode. Write whatever you want. So, word. Tab to exit the edit mode. Then over here on this sideline, you go inside of the text editor. We have geometry here. You can actually extrude it. Although, just know that by extruding it from here, the text also goes up. Um, that's that's not necessarily a problem. It really all depends on what you're going for. And it doesn't have to be this much extruded. Let's say this small. Next, we have alignment. So, I would say center and no, sorry, what am I doing? middle. There we go. Now, once we have this in place,

[13:53]
okay, that works pretty good. You would then right click on it and convert to mesh. This is where it is no longer a text layer. It is simply a mesh object. So, this is the destructive part. So, no more pressing tab to edit the word itself, but rather you can see the mesh here as it is. Now, this geometry is not ideal. For those of you who might be familiar with Blender, you might notice this is really not ideal. So, the next thing to do would go to the modifiers, add a modifier. It would be, I think, generate. And you go to remsh, switch to sharp. I'll put this on 7, I guess, and this to six. Uncheck the remove disconnected.

[14:40]
And let's see. 9. You can also go to the object, go to visibility and there should be a wireframe somewhere. Viewport display wireframe. So here we can see the geometry of it. We could say it be like well this is this is not too bad, right? Turn off wireframe. Go here and apply. So now we have our word with better geometry. And if you see the style of the text from the source video, it has this uh beveing in a way or embossing type

[15:26]
thing going on. So for this over here to do that, you go to edit mode, press one. I would activate the X-ray mode. Grab everything at the bottom here. Extrude. Bring it down. Let's say around here. Grab faces. I'm going to turn off the X-ray mode. Go back to this. I'm holding down alt and shift so I can grab all the faces like this. Alt E, extrude faces along normal. And then you can simply extrude them as such. Now, another thing I probably should have done before doing all of this would have been to grab all of these edges

[16:13]
here. So, again, alt shift and then clicking. And now I can go to individual origin scale, shift zed, and scale it up a bit so it has a bit of uh a curve sort of. And these might actually even be two highs. So, let's go ahead and grab all of this. Grab and lower as such just to give you an idea. The rest is well clearly this needed a better geometry, but anyways, the rest would be to, you know, add your coloring. Uh, you go inside of edit mode. Since we have the top here selected, you would add a

[16:58]
new shader. You would assign it so that this picks up this color. Then we can control I to invert. Create a new color, new material. Assign this there. And then if you go here, oops. Okay. We can now see how we have two different things. Now this second material here, I simply made it fully metallic so it has reflection. And then last but not least, inside of the world, I gave it a bit of purple so it would match our scene. And that's pretty much how I did it. Now, for rendering, I rendered as PNG. Now, this is pretty customary with uh 3D renders

[17:44]
because if anything goes wrong, having a PNG gives you a bit more flexibility. You don't have to start over. If you have to stop midway, you don't lose the progress, etc. for the transformation. With everything selected, you'd press P, select by loose parts, and then you can simply rotate everything, push it above, make it come back down, add your key frames, etc. All right, so that's pretty much it for the Blender part. So, I created the text, gave it its material, the animation, and then render it a PNG. Now, the reason why we're jumping into Kitten Live next is because Friction does not import image sequences. So now we need a video with transparent background. Now of course you could have rendered a video with transparent background using Blender, but like I

[18:29]
said, if anything goes wrong, you're losing the entire video. Instead of having a sequence of images that you can modify, start from the point of error or it's just standard and it can save you a lot of time depending on what you're rendering. All right, so let's jump inside of Kidden Live. So inside of Kitten Live here, basically all I did was bring in the image sequence. You already know how to do this. You navigate to your image sequence, import images, grab the first frame, press okay, and then you import everything. I placed it on the timeline, then controll enter to go to the render window. You have video with alpha. I chose the alpha. There's nothing really here to change necessarily. Maybe I should have uncheck audio because there's no audio.

[19:14]
Choose your destination and then render the file. And that's pretty much it for getting Live for this part. If I were to add sound, because I didn't add sound to the to the video or the project, if I were to add sound, I would definitely render it out from Friction and bring it into Kit and Live. Even if to just prepare the sound and then export it back to Frictions for the final render, all depends on your workflow. All all depends on um what works best for you and and where you want the final render to come from. I I said it in the previous video, working with audio inside of Friction is not ideal, but it is possible. You can totally do it. You can import audio in it and it gives you the same clip thing and you can move it

[20:00]
around so you can adjust your audio. So, it's totally doable. So now that we have the 3D text animation as a video with transparency, I simply imported it into friction. And then I added two raster effects to it. So the brightness and the shadow because I didn't make it bright enough in Blender. Not enough lights. So I added the brightness so it would be brighter. And then I used the shadow again to give it this glow. For the frame, I did use frame remapping simply because I didn't use this as a reference. So once I brought it in, I had to slow it down where I needed it to go slower and accelerate where I needed it to go faster. And that's pretty much

[20:45]
it. Now for the lightning, just so you know, if I zoom out here, you might be able to see the red outlines. Let me scale this down. And that is me deforming the lightning. So, rotating it and scaling it. And I also have a custom shader that I made for four corners that allowed me to pinch the corners. And uh I made the bottom of the lightning, this side a little wider. And I believe I did the same thing for this one as well. But yeah, now this is quickly put together. It's not really refined or I didn't really put much thought into it. The idea was stick to the source and show

[21:31]
how to execute it or basically just execute it and that's it. That's why I didn't even bother to look for different colors or anything of the sort. It was like reproduce it. And that's why this is very rough. You can do much better uh with your own original ideas, but it's just to show you that it's very doable. You have three amazing software at your disposal and a ton more when it comes to Foss. So free and open source software. So really the sky's is the limit. Now that's it for this video. You can click on this playlist here to learn more about getting Live. I have a Kofi link down in the description for those of you who like to support the channel. Now thanks for watching and I'll see you next time.
