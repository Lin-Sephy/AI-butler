/**
 * AI 身体状态计划管家 —— 像素空间 v0.2
 *
 * 当前状态：第一版空草地 + 角色走动 + 小鸡跟随
 * 用 Sprout Lands 素材包（已付费商用许可）
 * 技术栈：React + Vite + PixiJS v8
 *
 * 操作：WASD 或方向键移动
 */

import { useEffect, useRef } from 'react'
import { Application, Assets, Sprite, Texture, Rectangle } from 'pixi.js'

const SCALE = 3
const TILE = 16
const VIEW_W = 800
const VIEW_H = 600

export default function App() {
  const containerRef = useRef(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let app = null
    let detach = () => {}
    let destroyed = false

    ;(async () => {
      app = new Application()
      await app.init({
        width: VIEW_W,
        height: VIEW_H,
        background: '#86c26a',
        antialias: false,
        roundPixels: true,
      })
      if (destroyed) {
        app.destroy(true, { children: true })
        return
      }
      container.appendChild(app.canvas)

      const [grassTex, charTex, chickenTex] = await Promise.all([
        Assets.load('/assets/tilesets/grass.png'),
        Assets.load('/assets/characters/character.png'),
        Assets.load('/assets/animals/chicken.png'),
      ])
      // 像素风必须用 nearest，否则放大会糊
      for (const t of [grassTex, charTex, chickenTex]) {
        t.source.scaleMode = 'nearest'
      }

      // 草地纯草 tile（取 grass.png 中心区域一个纯绿 tile）
      const grassTile = new Texture({
        source: grassTex.source,
        frame: new Rectangle(16, 16, TILE, TILE),
      })

      // 铺满屏幕
      const cellSize = TILE * SCALE
      const cols = Math.ceil(VIEW_W / cellSize) + 1
      const rows = Math.ceil(VIEW_H / cellSize) + 1
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const s = new Sprite(grassTile)
          s.x = c * cellSize
          s.y = r * cellSize
          s.width = cellSize
          s.height = cellSize
          app.stage.addChild(s)
        }
      }

      // 角色 4 帧走路（第一行 = 面向下）
      const charFrames = []
      for (let i = 0; i < 4; i++) {
        charFrames.push(new Texture({
          source: charTex.source,
          frame: new Rectangle(i * 48, 0, 48, 48),
        }))
      }
      const char = new Sprite(charFrames[0])
      char.anchor.set(0.5, 0.5)
      char.width = 48 * SCALE
      char.height = 48 * SCALE
      char.x = VIEW_W / 2
      char.y = VIEW_H / 2
      app.stage.addChild(char)

      // 小鸡 idle（第一行前 2 帧，跟 v0.2 一样）
      const chickenIdle = []
      for (let i = 0; i < 2; i++) {
        chickenIdle.push(new Texture({
          source: chickenTex.source,
          frame: new Rectangle(i * 16, 0, 16, 16),
        }))
      }
      // 走路也先用 idle 那 2 帧（不换行，避免奇怪抖动）
      const chickenWalk = chickenIdle
      const chicken = new Sprite(chickenIdle[0])
      chicken.anchor.set(0.5, 0.5)
      chicken.width = 16 * SCALE
      chicken.height = 16 * SCALE
      chicken.x = char.x + 60
      chicken.y = char.y + 50
      app.stage.addChild(chicken)

      // 键盘输入
      const keys = {}
      const kd = e => { keys[e.key.toLowerCase()] = true }
      const ku = e => { keys[e.key.toLowerCase()] = false }
      window.addEventListener('keydown', kd)
      window.addEventListener('keyup', ku)

      // 主循环
      let frameCounter = 0
      const SPEED = 2.4

      // baseY：角色/小鸡的"真实脚底位置"（不含 bob 偏移）
      // 每帧渲染前先把 y 从 base 重算，加 bob 偏移后再赋值
      let charBaseY = char.y
      let chickenBaseY = chicken.y

      app.ticker.add(() => {
        frameCounter++

        // —— 角色移动 ——
        let dx = 0, dy = 0
        if (keys['w'] || keys['arrowup']) dy -= 1
        if (keys['s'] || keys['arrowdown']) dy += 1
        if (keys['a'] || keys['arrowleft']) dx -= 1
        if (keys['d'] || keys['arrowright']) dx += 1
        if (dx && dy) { dx *= 0.707; dy *= 0.707 }

        char.x += dx * SPEED
        charBaseY += dy * SPEED
        char.x = Math.max(30, Math.min(VIEW_W - 30, char.x))
        charBaseY = Math.max(30, Math.min(VIEW_H - 30, charBaseY))

        const moving = dx !== 0 || dy !== 0
        char.y = charBaseY
        if (moving) {
          const fi = Math.floor(frameCounter / 8) % 4
          char.texture = charFrames[fi]
          if (dx > 0) char.scale.x = SCALE
          else if (dx < 0) char.scale.x = -SCALE
        } else {
          char.texture = charFrames[0]
        }

        // —— 小鸡跟随 ——
        const gx = char.x - chicken.x
        const gy = char.y - chicken.y
        const gd = Math.hypot(gx, gy)
        const KEEP = 55
        if (gd > KEEP) {
          const spd = 1.7
          chicken.x += (gx / gd) * spd
          chickenBaseY += (gy / gd) * spd
          // 走路帧循环
          const ci = Math.floor(frameCounter / 8) % chickenWalk.length
          chicken.texture = chickenWalk[ci]
          if (gx > 0) chicken.scale.x = SCALE
          else if (gx < 0) chicken.scale.x = -SCALE
          chicken.y = chickenBaseY
        } else {
          // 原版静止：2 帧缓慢切换，不 bob
          const ci = Math.floor(frameCounter / 30) % chickenIdle.length
          chicken.texture = chickenIdle[ci]
          chicken.y = chickenBaseY
        }
      })

      detach = () => {
        window.removeEventListener('keydown', kd)
        window.removeEventListener('keyup', ku)
      }
    })()

    return () => {
      destroyed = true
      detach()
      // 不在这里直接 destroy：async init 可能还没完成，直接 destroy 会炸
      // 交给 init 流程里的 destroyed 判断处理，或下面兜底
      try {
        if (app && app.renderer) app.destroy(true, { children: true })
      } catch {}
    }
  }, [])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: '14px',
      }}
    >
      <div
        ref={containerRef}
        style={{
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          borderRadius: '4px',
          overflow: 'hidden',
          lineHeight: 0,
        }}
      />
      <div style={{ color: '#8a9a78', fontSize: '11px', letterSpacing: '2px' }}>
        WASD / 方向键移动 · AI 身体状态计划管家 · 像素空间 v0.2
      </div>
    </div>
  )
}
