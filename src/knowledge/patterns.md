# Strudel Pattern Recipes

Idiomatic snippets the chaos agent can recombine or remix.

## Drums

```js
// Classic 4-on-the-floor
s("bd*4, [~ sd]*2, hh*8").bank("RolandTR909")

// Breakbeat
s("bd ~ ~ sd, hh*16, ~ ~ ~ oh").bank("AkaiLinn")

// Trap-ish hats
s("hh*16").gain("0.5 0.8 0.4 0.9").bank("RolandTR808")

// Half-time stomp
s("bd ~ ~ ~, ~ ~ sd ~").bank("RolandTR707")
```

## Bass

```js
// Acid-ish bassline
n("<0 7 3 10>*8").scale("C:minor")
  .s("sawtooth").lpf(sine.range(200, 1800).slow(4)).lpq(8)

// Walking jazz bass
note("<c2 a1 d2 g1>*4").s("gm_acoustic_bass")
```

## Chords / pads

```js
note("<[c,eb,g] [ab,c,eb] [g,bb,d] [f,ab,c]>").s("gm_pad_2_warm").room(0.6)

note("[c,e,g] ~ [d,f,a] ~ [e,g,b] ~ ~ [c,e,g]").s("piano").room(0.3)
```

## Arpeggios

```js
n("0 2 4 7 4 2").scale("C:lydian").s("triangle").release(0.2)

note("c(3,8) <e g> f(5,8,1)").scale("C:major").s("triangle")
```

## Polyrhythm

```js
note("c*3, e*4, g*5").s("sawtooth").lpf(800)
```

## Texture / FX

```js
s("hh*16").vowel("<a e i o u>").room(0.4)

n("0 .. 8").scale("C:minor").s("sine")
  .delay(0.6).delaytime("0.25:0.5:0.8").delayfeedback(0.7)
```

## Generative-friendly idioms

```js
// Random pick per cycle:
s("<bd sd cp rim cb>?0.7")

// Conditional transform:
s("bd*4").every(4, x => x.fast(2)).bank("RolandTR909")

// Layer with juxtaposed reverse:
n("0 2 4 7").scale("C:dorian").s("supersaw").jux(rev)
```
