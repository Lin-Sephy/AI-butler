/**
 * AI 身体状态计划管家 —— 像素空间 v0.3
 *
 * 当前状态：加了场景切换骨架（卧室 / 书房 / 菜园）
 * 三个场景都是空的，差异只是背景色（下一版填物件）
 * 角色在每个场景记住上次位置，小鸡跨场景跟着你走
 *
 * 操作：WASD / 方向键移动，顶部按钮切场景
 */

import { useEffect, useRef, useState } from 'react'
import { Application, Assets, Sprite, Texture, Rectangle, Container } from 'pixi.js'

const SCALE = 3
const TILE = 16
const VIEW_W = 800
const VIEW_H = 600

// 场景定义：先只有背景色差异，物件后面填
// showGrass: 是否铺草地 tile（室外 true，室内 false）
const SCENES = [
  { id: 'bedroom', label: '卧室', bg: 0xe8c4cc, showGrass: false },
  { id: 'study',   label: '书房', bg: 0xc9a87a, showGrass: false },
  { id: 'garden',  label: '菜园', bg: 0x86c26a, showGrass: true  },
]
const DEFAULT_SCENE = 'garden'

export default function App() {
  const containerRef = useRef(null)
  const [sceneId, setSceneId] = useState(DEFAULT_SCENE)
  const sceneIdRef = useRef(sceneId)
  // 每个场景下角色和小鸡的位置
  const positionsRef = useRef({})
  // PixiJS app + 关键对象的引用，按钮回调可以摸到它们
  const pixiRef = useRef(null)

  // 场景切换响应
  useEffect(() => {
    const pixi = pixiRef.current
    if (!pixi) return
    const { app, char, chicken, tileLayer, getCharBaseY, setCharBaseY, getChickenBaseY, setChickenBaseY } = pixi

    // 保存旧场景位置
    const oldId = sceneIdRef.current
    positionsRef.current[oldId] = {
      charX: char.x,
      charY: getCharBaseY(),
      chickenX: chicken.x,
      chickenY: getChickenBaseY(),
    }

    // 切换到新场景
    sceneIdRef.current = sceneId
    const scene = SCENES.find(s => s.id === sceneId)
    app.renderer.background.color = scene.bg
    tileLayer.visible = scene.showGrass

    // 恢复新场景角色位置（没有就用默认中心）
    const saved = positionsRef.current[sceneId]
    if (saved) {
      char.x = saved.charX
      setCharBaseY(saved.charY)
      chicken.x = saved.chickenX
      setChickenBaseY(saved.chickenY)
    } else {
      char.x = VIEW_W / 2
      setCharBaseY(VIEW_H / 2)
      chicken.x = VIEW_W / 2 + 60
      setChickenBaseY(VIEW_H / 2 + 50)
    }
  }, [sceneId])

  // PixiJS 初始化（只跑一次）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let app = null
    let detach = () => {}
    let destroyed = false

    ;(async () => {
      app = new Application()
      const initScene = SCENES.find(s => s.id === DEFAULT_SCENE)
      await app.init({
        width: VIEW_W,
        height: VIEW_H,
        background: initScene.bg,
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
      for (const t of [grassTex, charTex, chickenTex]) {
        t.source.scaleMode = 'nearest'
      }

      // 草地 tile 层（目前三个场景都用这一层，之后每个场景各自铺）
      const tileLayer = new Container()
      app.stage.addChild(tileLayer)
      const grassTile = new Texture({
        source: grassTex.source,
        frame: new Rectangle(16, 16, TILE, TILE),
      })
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
          tileLayer.addChild(s)
        }
      }

      // 角色
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

      // 小鸡
      const chickenIdle = []
      for (let i = 0; i < 2; i++) {
        chickenIdle.push(new Texture({
          source: chickenTex.source,
          frame: new Rectangle(i * 16, 0, 16, 16),
        }))
      }
      const chickenWalk = chickenIdle
      const chicken = new Sprite(chickenIdle[0])
      chicken.anchor.set(0.5, 0.5)
      chicken.width = 16 * SCALE
      chicken.height = 16 * SCALE
      chicken.x = char.x + 60
      chicken.y = char.y + 50
      app.stage.addChild(chicken)

      // 键盘
      const keys = {}
      const kd = e => { keys[e.key.toLowerCase()] = true }
      const ku = e => { keys[e.key.toLowerCase()] = false }
      window.addEventListener('keydown', kd)
      window.addEventListener('keyup', ku)

      let frameCounter = 0
      const SPEED = 2.4
      let charBaseY = char.y
      let chickenBaseY = chicken.y

      // 暴露给切换 effect
      pixiRef.current = {
        app, char, chicken, tileLayer,
        getCharBaseY: () => charBaseY,
        setCharBaseY: (v) => { charBaseY = v },
        getChickenBaseY: () => chickenBaseY,
        setChickenBaseY: (v) => { chickenBaseY = v },
      }

      app.ticker.add(() => {
        frameCounter++

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

        const gx = char.x - chicken.x
        const gy = char.y - chicken.y
        const gd = Math.hypot(gx, gy)
        const KEEP = 55
        if (gd > KEEP) {
          const spd = 1.7
          chicken.x += (gx / gd) * spd
          chickenBaseY += (gy / gd) * spd
          const ci = Math.floor(frameCounter / 8) % chickenWalk.length
          chicken.texture = chickenWalk[ci]
          if (gx > 0) chicken.scale.x = SCALE
          else if (gx < 0) chicken.scale.x = -SCALE
          chicken.y = chickenBaseY
        } else {
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
      try {
        if (app && app.renderer) app.destroy(true, { children: true })
      } catch {}
      pixiRef.current = null
    }
  }, [])

  const btnStyle = (active) => ({
    background: active ? '#f0e4b0' : '#2a2a36',
    color: active ? '#2a2a36' : '#c8c0a8',
    border: 'none',
    padding: '8px 22px',
    fontFamily: 'inherit',
    fontSize: '13px',
    letterSpacing: '3px',
    cursor: 'pointer',
    borderRadius: '4px',
    transition: 'all 0.15s',
  })

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
      <div style={{ display: 'flex', gap: '10px' }}>
        {SCENES.map(s => (
          <button
            key={s.id}
            style={btnStyle(sceneId === s.id)}
            onClick={() => setSceneId(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>
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
        WASD / 方向键移动 · AI 身体状态计划管家 · 像素空间 v0.3
      </div>
    </div>
  )
}
