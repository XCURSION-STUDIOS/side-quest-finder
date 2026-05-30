import React from 'react'
import { motion } from 'framer-motion'

export default function XCursionLogo({ size = 112, staticMode = false }){
  const shapes = [
    { type: 'diamond', cx: 166, cy: 52, half: 52, delay: 0 },
    { type: 'circle', cx: 166, cy: 157, r: 18 },
    { type: 'diamond', cx: 61, cy: 157, half: 52, delay: 0.14 },
    { type: 'diamond', cx: 271, cy: 157, half: 52, delay: 0.14 },
    { type: 'diamond', cx: 166, cy: 262, half: 52, delay: 0.28 },
    { type: 'circle', cx: 166, cy: 367, r: 18 },
    { type: 'diamond', cx: 61, cy: 367, half: 52, delay: 0.42 },
    { type: 'diamond', cx: 271, cy: 367, half: 52, delay: 0.42 },
  ]

  const width = size
  const height = Math.round(size * (472 / 372))

  function renderStaticShape(shape, index, props = {}){
    if(shape.type === 'circle'){
      return (
        <circle
          key={`static-${index}`}
          cx={shape.cx}
          cy={shape.cy}
          r={shape.r}
          {...props}
        />
      )
    }

    const side = shape.half * 2
    return (
      <rect
        key={`static-${index}`}
        x={shape.cx - shape.half}
        y={shape.cy - shape.half}
        width={side}
        height={side}
        rx={8}
        transform={`rotate(45 ${shape.cx} ${shape.cy})`}
        {...props}
      />
    )
  }

  function renderHatch(width, top, bottom){
    const count = Math.ceil((bottom - top) / 9) + 2

    return Array.from({ length: count }).map((_, index) => (
      <line
        key={index}
        x1={-width}
        x2={width}
        y1={top + index * 9}
        y2={top + index * 9}
        stroke="#000"
        strokeWidth="3.2"
      />
    ))
  }

  function renderVisibleShape(shape, index){
    if(shape.type === 'circle'){
      return (
        <g key={`visible-${index}`} transform={`translate(${shape.cx} ${shape.cy})`}>
          <circle r={shape.r} fill="url(#logoSheen)" />
          <g clipPath={`url(#localCircleClip-${index})`} opacity="0.76">
            {renderHatch(shape.r + 4, -shape.r - 4, shape.r + 4)}
          </g>
        </g>
      )
    }

    const side = shape.half * 2

    return (
      <g key={`visible-${index}`} transform={`translate(${shape.cx} ${shape.cy})`}>
        <g transform="rotate(45)">
          {!staticMode && (
            <animateTransform
              attributeName="transform"
              type="rotate"
              values="45;45;405;405;45"
              keyTimes="0;0.54;0.68;0.76;1"
              dur="10.6s"
              begin={`${shape.delay}s`}
              repeatCount="indefinite"
            />
          )}
          <rect
            x={-shape.half}
            y={-shape.half}
            width={side}
            height={side}
            rx={8}
            fill="url(#logoSheen)"
          />
          <svg
            x={-shape.half}
            y={-shape.half}
            width={side}
            height={side}
            viewBox={`${-shape.half} ${-shape.half} ${side} ${side}`}
            overflow="hidden"
            opacity="0.76"
          >
            <g transform="rotate(-45)">
              {renderHatch(shape.half * 2, -shape.half * 2, shape.half * 2)}
            </g>
          </svg>
        </g>
      </g>
    )
  }

  return (
    <motion.svg
      className="xcursion-logo"
      width={width}
      height={height}
      viewBox="-20 -20 372 472"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      animate={staticMode ? undefined : {
        filter: [
          'drop-shadow(0 0 0 rgba(255,255,255,0))',
          'drop-shadow(0 0 10px rgba(255,255,255,0.22))',
          'drop-shadow(0 0 0 rgba(255,255,255,0))',
        ],
      }}
      transition={staticMode ? undefined : { duration: 4.5, repeat: Infinity, ease: 'easeInOut' }}
    >
      <defs>
        <linearGradient id="logoSheen" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="48%" stopColor="#d8d8d8" />
          <stop offset="100%" stopColor="#ffffff" />
        </linearGradient>

        {shapes.map((shape, index) => {
          if(shape.type === 'circle'){
            return (
              <clipPath id={`localCircleClip-${index}`} key={`clip-${index}`}>
                <circle r={shape.r} />
              </clipPath>
            )
          }

          return (
            <clipPath id={`localDiamondClip-${index}`} key={`clip-${index}`}>
              <rect
                x={-shape.half}
                y={-shape.half}
                width={shape.half * 2}
                height={shape.half * 2}
                rx={8}
              />
            </clipPath>
          )
        })}

        <mask id="logoSilhouetteMask">
          <rect x="-20" y="-20" width="372" height="472" fill="#000" />
          {shapes.map((shape, index) => renderStaticShape(shape, index, { fill: '#fff' }))}
        </mask>

        <filter id="chromaticSoft" x="-24%" y="-18%" width="148%" height="136%">
          <feFlood floodColor="#ff2d7a" floodOpacity="0.34" result="red" />
          <feFlood floodColor="#24d8ff" floodOpacity="0.30" result="cyan" />
          <feComposite in="red" in2="SourceAlpha" operator="in" result="redShape" />
          <feComposite in="cyan" in2="SourceAlpha" operator="in" result="cyanShape" />
          <feOffset in="redShape" dx="-2.2" dy="0.8" result="redOffset" />
          <feOffset in="cyanShape" dx="2.1" dy="-0.7" result="cyanOffset" />
          <feMerge>
            <feMergeNode in="redOffset" />
            <feMergeNode in="cyanOffset" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <linearGradient id="logoSweep" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="45%" stopColor="#ffffff" stopOpacity="0.42" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <motion.g
        initial={staticMode ? false : { opacity: 0, scale: 0.94 }}
        animate={staticMode ? { opacity: 1, scale: 1 } : { opacity: 1, scale: [1, 1.025, 1] }}
        transition={staticMode ? undefined : {
          opacity: { duration: 0.45 },
          scale: { duration: 5, repeat: Infinity, ease: 'easeInOut' },
        }}
        style={{ transformOrigin: '166px 216px' }}
      >
        <g filter="url(#chromaticSoft)">
          {shapes.map((shape, index) => renderVisibleShape(shape, index))}
        </g>

        {!staticMode && (
          <motion.rect
            x="-72"
            y="-38"
            width="112"
            height="528"
            fill="url(#logoSweep)"
            mask="url(#logoSilhouetteMask)"
            initial={{ x: -180, opacity: 0 }}
            animate={{ x: [-180, 404], opacity: [0, 0.22, 0] }}
            transition={{ duration: 5.8, repeat: Infinity, repeatDelay: 1.8, ease: 'easeInOut' }}
            transform="rotate(18 166 216)"
          />
        )}
      </motion.g>
    </motion.svg>
  )
}
