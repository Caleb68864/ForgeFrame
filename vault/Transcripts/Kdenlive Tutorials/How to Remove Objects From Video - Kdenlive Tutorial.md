---
title: "How to Remove Objects From Video - Kdenlive Tutorial"
video_id: d8gj-DjdWgM
url: https://www.youtube.com/watch?v=d8gj-DjdWgM
channel: Nuxttux Creative Studio
playlist: kdenlive-tutorials
uploaded: 2024-05-06
duration: 3:07
type: reference
tags: [kdenlive, tutorial, transcript]
---
# How to Remove Objects From Video - Kdenlive Tutorial

## Transcript
[00:00]
here is how you can easily remove objects from the background of your videos it's a neat trick that works best with static or tripod footage although you can make it work with minimal camera motion as long as the lighting in the scene doesn't change we'll start simple with something static the first shot here is a tripod shot the lighting is constant and nothing moves in front of the objects that we want to remove this is an ideal scenario or remove the board and the clock from the background with our clip selected I'll go to the effects Tab and look for mask we can either use a rot scoping mask for complex shapes or an alpha shaped mask for simpler shapes such as rectangles ellipse or triangles I'll use the alpha shapes mask for this one next I'll add a mask apply and finally I'll add a transform effect between these two using the on canvus

[00:45]
controls I'll place the alpha shape over the board on the wall making sure to cover it well this is to measure the size of it you can disable the mask apply to see what's being selected and check the fettering of the edges which can be adjusted using the transition whiff slider once the size is right move the shape over to an area of the background that will be used to cover the objects so I'll move the shape to the side here now moving on to the transform I'll adjust the X and Y values to place the patch over the objects that we want to cover that's it simply adjust the fettering size and position as needed you can either extend the first Alpha shape or make a new stack with the same effects and use the ellipse shape to cover the clock moving on to a clip with some camera motion I'll be removing the clock on the wall it's a similar process except that we'll be extracting

[01:31]
a frame from the footage and doing some minor tracking I'll place the play head at the start of our clip right click on the monitor select extract frame to project I recommend saving the image in the same folder as your current project or rename this and click save now we have the frame in our project bin I'll place the image over the clip match the length add similar effects minus the mask apply which means you can either use a rotoscoping mask or simply a normal Alpha shapes I'll set the shape of the alpha shape ellipse and place the alpha shape over the clock to check the size and then I'll move it to the side I'll temporarily disable the top track and add a motion tracker to the video clip underneath track something relatively close to the object that you want to remove in my case I'll track the clock itself once tracked copy all key

[02:16]
frames to clipboard by clicking on the hamburger menu I'll disable the tracker and enable the top track now let's import the key frames to the transform effect click on the hamburger menu and import key frames uncheck limit key frame number set map to position I'll choose top Center for both options finally adjust the position offset until the patch is over the clock on the wall you might notice that the patch that we placed over the clock is slightly brighter than the rest of the wall for this I'll add a levels effect right under the transform and then I'll adjust the gamma push it down ever so slightly just to match the brightness and now for convenience I plac these two clips inside of a sequence of their own and there we have it you can click on this playlist here for more kiding life tutorials this is Nu duck creative

[03:02]
Studio thanks for watching
