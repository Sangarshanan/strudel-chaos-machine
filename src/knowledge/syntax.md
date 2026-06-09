# Strudel Mini-Notation Reference

A condensed cheat sheet for Strudel pattern syntax. Use inside the
quoted string passed to `note(...)`, `sound(...)`, `s(...)`, or `n(...)`.

## 1. Basic sequences

```js
note("c e g b")              // 4 notes evenly spaced over one cycle
note("c d e f g a b")        // 7 notes squeezed into one cycle
```

## 2. Subdivisions with `[ ]`

Group events to share a time slot:

```js
note("c [e g] a")            // c | (e g) | a
note("c [e [g b]] d")        // nested subdivisions
```

## 3. Slow sequences with `< >`

Play one element per cycle (alternation across cycles):

```js
note("<c e g b>")            // one note per cycle, repeating
note("<c e g b>*4")          // collapse into single cycle
```

## 4. Multiplication `*`

Repeat / speed up:

```js
note("c*4 e*2 g")            // c c c c e e g
note("[c e g]*2")            // group plays twice as fast
sound("bd*32")               // very fast → pitched
```

## 5. Division `/`

Stretch across multiple cycles:

```js
note("[c e g b]/2")          // pattern takes 2 cycles
```

## 6. Elongation `@`

```js
note("c@3 eb")               // c lasts 3 units, eb lasts 1
note("c@2 e g@2")
```

## 7. Replication `!`

Repeat a token without changing total time:

```js
note("c!2 e g")              // c c e g
note("c!2 [eb,g]")
```

## 8. Euclidean rhythms `(hits, steps[, rotation])`

```js
note("c(3,8)")               // 3 hits across 8 steps
note("c(5,8)")
note("c(3,8,1)")             // rotated by 1
```

## 9. Parallel layers `,`

Inside a bracket or at the top level:

```js
note("c e g, a f d")         // two patterns at once
note("[c,e,g]")              // chord: stacked simultaneously
note("c e g, a f")           // 3-against-2 polyrhythm
```

## 10. Alternation `|`

Pick one option per cycle:

```js
note("c | e | g")
note("[c e] | [g b] | [d f]")
```

## 11. Degradation `?`

```js
note("c e g b?")             // b has 50% chance
note("c e g b?0.2")          // explicit probability
note("[c e g b]*8?")         // degrade whole group
```

## Rests

`~` is a silence (rest) of one event slot:

```js
note("c ~ e ~ g ~")
```

## Common method chains

```js
note("c e g").s("piano").room(0.4)
sound("bd sd").bank("RolandTR909").lpf(800)
n("0 2 4 7").scale("C:minor").s("sawtooth").gain(0.6)
```
