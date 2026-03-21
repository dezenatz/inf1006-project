import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Slider } from './components/Slider'
import './index.css'

const API_BASE = 'http://192.168.1.100:5000'   // ← Pi 1 IP

const DEFAULT_ROOM_CONFIGS = {
  'living-room': {
    temp_fan_threshold: 30, temp_ac_threshold: 35,
    pir_timeout_sec: 30, manual_override_sec: 120,
    night_start: '19:30', night_end: '07:30',
  },
  bedroom: {
    temp_ac_threshold: 35,
    pir_timeout_sec: 30, manual_override_sec: 120,
    night_start: '19:30', night_end: '07:30',
  },
  kitchen: {
    pir_timeout_sec: 30,
  },
}

// ─── Palette ──────────────────────────────────────────────────────────────────

const C = {
  bg: '#F5F5F3',
  card: '#FFFFFF',
  textPri: '#1C1C1E',
  textSec: '#8E8E93',
  textMute: '#C7C7CC',
  pillBg: '#F7F7F5',
  border: '#F2F2F7',
  green: '#34C759',
  greenBg: '#F0FAF3',
  toggleOff: '#D1D1D6',
  wall: '#DDDDD8',
}

// ─── Icons ────────────────────────────────────────────────────────────────────

const TvIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2.5" />
    <path d="M8 21h8M12 17v4" />
  </svg>
)

const AcIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2v20M2 12h20" />
    <path d="M5 5l14 14M19 5 5 19" />
  </svg>
)

const FanIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="2" />
    <path d="M12 2a3 3 0 0 1 3 3c0 1.5-.8 2.8-2 3.5" />
    <path d="M22 12a3 3 0 0 1-3 3c-1.5 0-2.8-.8-3.5-2" />
    <path d="M12 22a3 3 0 0 1-3-3c0-1.5.8-2.8 2-3.5" />
    <path d="M2 12a3 3 0 0 1 3-3c1.5 0 2.8.8 3.5 2" />
  </svg>
)

const ThermoIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />
  </svg>
)

const DropIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
  </svg>
)

const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
)

const BeakerIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 3h6M9 3v7l-5 9a1 1 0 0 0 .9 1.5h14.2a1 1 0 0 0 .9-1.5L15 10V3" />
    <path d="M7.5 16h9" />
  </svg>
)

const ChevronIcon = ({ open }) => (
  <motion.svg
    animate={{ rotate: open ? 180 : 0 }}
    transition={{ duration: 0.25 }}
    width="14" height="14" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
  >
    <path d="M6 9l6 6 6-6" />
  </motion.svg>
)

const LampIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 2h6l2 7H7L9 2z" />
    <path d="M12 9v13M8 22h8" />
  </svg>
)

const GearIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
)

const ICON_MAP = { tv: TvIcon, ac: AcIcon, fan: FanIcon, lamp: LampIcon }


// ─── Top-down appliance illustrations ─────────────────────────────────────────

const TvTopDown = () => <img src="/Tv.webp" width="105" height="105" style={{ display: 'block', objectFit: 'contain' }} />
const AcTopDown = () => <img src="/ac.png" width="100" height="100" style={{ display: 'block', objectFit: 'contain' }} />
const FanTopDown = () => <img src="/fan.png" width="64" height="64" style={{ display: 'block', objectFit: 'contain' }} />
const LampTopDown = () => <img src="/lamp.png" width="40" height="40" style={{ display: 'block', objectFit: 'contain' }} />

const TOP_DOWN_MAP = { tv: TvTopDown, ac: AcTopDown, fan: FanTopDown, lamp: LampTopDown }


// ─── Data ─────────────────────────────────────────────────────────────────────

const INITIAL_ROOMS = [
  {
    id: 'living-room',
    name: 'Living Room',
    pi: 'Pi 1',
    occupied: null,
    temp: null,
    humidity: null,
    hasDHT: true,
    hasIR: true,
    appliances: [
      { id: 'tv', name: 'TV', icon: 'tv', on: false },
      { id: 'ac', name: 'AC', icon: 'ac', on: false },
      { id: 'fan', name: 'Fan', icon: 'fan', on: false },
      { id: 'lamp', name: 'Lamp', icon: 'lamp', on: false },
    ],
  },
  {
    id: 'bedroom',
    name: 'Bedroom',
    pi: 'Pi 2',
    occupied: null,
    temp: null,
    humidity: null,
    hasDHT: true,
    hasIR: true,
    appliances: [
      { id: 'ac', name: 'AC', icon: 'ac', on: false },
      { id: 'lamp', name: 'Lamp', icon: 'lamp', on: false },
    ],
  },
  {
    id: 'kitchen',
    name: 'Kitchen',
    pi: 'Pi 3',
    occupied: null,
    hasDHT: false,
    hasIR: false,
    appliances: [
      { id: 'lamp', name: 'Lamp', icon: 'lamp', on: false },
    ],
  },
]

// ─── Floor plan layout ────────────────────────────────────────────────────────

const ROOM_LAYOUTS = [
  {
    id: 'living-room',
    bg: '/living%20room.png',
    appliances: [
      { id: 'fan', x: '50%', y: '48%' },
      { id: 'ac', x: '50%', y: '7%' },
      { id: 'tv', x: '50%', y: '92%' },
      { id: 'lamp', x: '88%', y: '88%' },
    ],
  },
  {
    id: 'bedroom',
    bg: '/bedroom.png',
    appliances: [
      { id: 'ac', x: '50%', y: '7%' },
      { id: 'lamp', x: '92%', y: '88%' },
    ],
  },
  {
    id: 'kitchen',
    bg: '/kitchen.png',
    appliances: [
      { id: 'lamp', x: '10%', y: '94%' },
    ],
  },
]

// ─── Toggle ───────────────────────────────────────────────────────────────────

function Toggle({ on, onChange, disabled }) {
  return (
    <motion.div
      onClick={!disabled ? () => onChange(!on) : undefined}
      animate={{ backgroundColor: on && !disabled ? C.green : C.toggleOff }}
      transition={{ duration: 0.2 }}
      style={{
        width: 46, height: 28, borderRadius: 14,
        padding: '0 3px', display: 'flex', alignItems: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : 1, flexShrink: 0,
      }}
    >
      <motion.div
        animate={{ x: on ? 18 : 0 }}
        transition={{ type: 'spring', stiffness: 600, damping: 32 }}
        style={{
          width: 22, height: 22, borderRadius: '50%',
          backgroundColor: '#fff', boxShadow: '0 1px 6px rgba(0,0,0,0.15)',
        }}
      />
    </motion.div>
  )
}

// ─── Occupancy Dot ────────────────────────────────────────────────────────────

function OccupancyDot({ occupied }) {
  return (
    <div style={{ position: 'relative', width: 8, height: 8, flexShrink: 0 }}>
      {occupied && (
        <motion.div
          animate={{ scale: [1, 2.6, 1], opacity: [0.3, 0, 0.3] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
          style={{ position: 'absolute', inset: 0, borderRadius: '50%', backgroundColor: C.green }}
        />
      )}
      <motion.div
        animate={{ backgroundColor: occupied ? C.green : C.toggleOff }}
        transition={{ duration: 0.3 }}
        style={{ width: 8, height: 8, borderRadius: '50%', position: 'relative' }}
      />
    </div>
  )
}

// ─── Sensor Pill ──────────────────────────────────────────────────────────────

function SensorPill({ icon, value }) {
  return (
    <div style={{
      flex: 1, backgroundColor: C.pillBg, borderRadius: 14,
      padding: '11px 13px', display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <span style={{ color: C.textSec, display: 'flex' }}>{icon}</span>
      <span style={{ fontSize: 16, fontWeight: 700, color: C.textPri }}>{value}</span>
    </div>
  )
}

// ─── Room Card ────────────────────────────────────────────────────────────────

function RoomCard({ room, onToggleAppliance, awayMode, index, config, onConfigChange }) {
  const [autoOpen, setAutoOpen] = useState(false)
  const occupied = room.occupied === true && !awayMode
  const hasFan = room.appliances.some(a => a.id === 'fan')

  const SectionLabel = ({ children }) => (
    <div style={{
      fontSize: 10, fontWeight: 700, color: C.textMute,
      letterSpacing: '0.6px', textTransform: 'uppercase', marginBottom: 10,
    }}>
      {children}
    </div>
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{
        backgroundColor: C.card, borderRadius: 28,
        padding: '24px 24px 20px',
        boxShadow: '0 2px 24px rgba(0,0,0,0.05)',
        display: 'flex', flexDirection: 'column', gap: 16,
      }}
    >
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 700, color: C.textPri, letterSpacing: '-0.2px' }}>
            {room.name}
          </div>
          <div style={{ fontSize: 12, color: C.textMute, marginTop: 3, fontWeight: 500 }}>
            {room.pi}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
          <OccupancyDot occupied={occupied} />
          <span style={{ fontSize: 12, fontWeight: 600, color: C.textMute }}>
            {awayMode ? 'Away' : room.occupied === null ? 'No data' : occupied ? 'Occupied' : 'Empty'}
          </span>
          <motion.button
            onClick={() => setAutoOpen(p => !p)}
            animate={{ color: autoOpen ? C.textPri : C.textMute, rotate: autoOpen ? 45 : 0 }}
            transition={{ duration: 0.2 }}
            style={{
              background: 'none', border: 'none', padding: 4, cursor: 'pointer',
              display: 'flex', alignItems: 'center', borderRadius: 6,
              backgroundColor: autoOpen ? C.pillBg : 'transparent',
            }}
          >
            <GearIcon />
          </motion.button>
        </div>
      </div>

      {/* ── DHT pills ── */}
      {room.hasDHT && (
        <div style={{ display: 'flex', gap: 8 }}>
          {[
            { icon: <ThermoIcon />, value: room.temp != null ? `${room.temp}°C` : '—' },
            { icon: <DropIcon />, value: room.humidity != null ? `${room.humidity}%` : '—' },
          ].map(({ icon, value }, i) => (
            <SensorPill key={i} icon={icon} value={value} />
          ))}
        </div>
      )}

      {/* ── Appliances ── */}
      {room.appliances.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {room.appliances.map((appliance) => {
            const Icon = ICON_MAP[appliance.icon] || (() => null)
            const disabled = awayMode || (appliance.icon !== 'lamp' && !room.hasIR)
            const active = appliance.on && !disabled
            return (
              <div key={appliance.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                paddingTop: 12, borderTop: `1px solid ${C.border}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <motion.div
                    animate={{ backgroundColor: active ? '#F0F0EE' : C.pillBg, color: active ? C.textPri : C.textMute }}
                    transition={{ duration: 0.2 }}
                    style={{ width: 32, height: 32, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <Icon />
                  </motion.div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: C.textPri }}>{appliance.name}</div>
                    {!room.hasIR && appliance.icon !== 'lamp' && (
                      <div style={{ fontSize: 11, color: C.textMute, marginTop: 1 }}>IR pending</div>
                    )}
                  </div>
                </div>
                <Toggle
                  on={appliance.on}
                  onChange={(val) => onToggleAppliance(room.id, appliance.id, val)}
                  disabled={disabled}
                />
              </div>
            )
          })}
        </div>
      )}

      {!room.hasDHT && room.appliances.length === 0 && (
        <div style={{
          backgroundColor: C.pillBg, borderRadius: 14, padding: '12px 14px',
          fontSize: 13, fontWeight: 500, color: C.textSec, textAlign: 'center',
        }}>
          Presence indicator only
        </div>
      )}

      {/* ── Automation expansion ── */}
      <AnimatePresence initial={false}>
        {autoOpen && config && (
          <motion.div
            key="auto"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              paddingTop: 16, borderTop: `1px solid ${C.border}`,
              display: 'flex', flexDirection: 'column', gap: 16,
            }}>

              {/* Temperature rules (rooms with DHT) */}
              {room.hasDHT && (
                <div>
                  <SectionLabel>Temperature</SectionLabel>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {hasFan && (
                      <SimSlider
                        label="Fan on at" value={config.temp_fan_threshold}
                        min={20} max={40} step={1} unit="°C"
                        onChange={val => onConfigChange({ ...config, temp_fan_threshold: val })}
                      />
                    )}
                    <SimSlider
                      label="AC on at" value={config.temp_ac_threshold}
                      min={25} max={45} step={1} unit="°C"
                      onChange={val => onConfigChange({ ...config, temp_ac_threshold: val })}
                    />
                  </div>
                </div>
              )}

              {/* Presence */}
              <div>
                <SectionLabel>Presence</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <SimSlider
                    label="Mark empty after" value={config.pir_timeout_sec}
                    min={10} max={600} step={10} unit="s"
                    onChange={val => onConfigChange({ ...config, pir_timeout_sec: val })}
                  />
                  {config.manual_override_sec !== undefined && (
                    <SimSlider
                      label="Manual override" value={config.manual_override_sec}
                      min={30} max={3600} step={30} unit="s"
                      onChange={val => onConfigChange({ ...config, manual_override_sec: val })}
                    />
                  )}
                </div>
              </div>

              {/* Night mode (rooms with DHT) */}
              {room.hasDHT && (
                <div>
                  <SectionLabel>Night Mode — lamp auto-on</SectionLabel>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <TimeField
                      label="Night starts" value={config.night_start}
                      onChange={val => onConfigChange({ ...config, night_start: val })}
                    />
                    <TimeField
                      label="Night ends" value={config.night_end}
                      onChange={val => onConfigChange({ ...config, night_end: val })}
                    />
                  </div>
                </div>
              )}

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ─── Floor Plan ───────────────────────────────────────────────────────────────


function ApplianceMarker({ appId, on, onClick }) {
  const TopDown = TOP_DOWN_MAP[appId]
  if (!TopDown) return null
  return (
    <motion.div
      onClick={e => { e.stopPropagation(); onClick() }}
      animate={{
        filter: on
          ? 'grayscale(0%) drop-shadow(0 3px 8px rgba(0,0,0,0.28))'
          : 'grayscale(100%)',
        opacity: on ? 1 : 0.3,
      }}
      whileHover={{
        filter: on
          ? 'grayscale(0%) drop-shadow(0 4px 12px rgba(0,0,0,0.35))'
          : 'grayscale(60%)',
        opacity: on ? 1 : 0.55,
        scale: 1.08,
      }}
      whileTap={{ scale: 0.93 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      style={{ cursor: 'pointer', display: 'inline-flex' }}
    >
      <TopDown />
    </motion.div>
  )
}

function SimSlider({ label, value, min, max, step, unit, onChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 500, color: C.textSec }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: C.textPri }}>
          {value != null ? `${value}${unit}` : '—'}
        </span>
      </div>
      <Slider
        value={[value ?? min]}
        min={min} max={max} step={step}
        tooltipContent={v => `${v}${unit}`}
        onValueChange={([v]) => onChange(v)}
      />
    </div>
  )
}

function TimeField({ label, value, onChange }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 12, fontWeight: 500, color: C.textSec }}>{label}</span>
      <input
        type="time"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="time-input"
      />
    </div>
  )
}

function FloorPlan({ rooms, onUpdateRoom }) {
  const [selected, setSelected] = useState(null)
  const roomMap = Object.fromEntries(rooms.map(r => [r.id, r]))
  const selRoom = selected ? roomMap[selected] : null

  const toggleAppliance = (roomId, appId) => {
    const room = roomMap[roomId]
    onUpdateRoom(roomId, {
      appliances: room.appliances.map(a =>
        a.id === appId ? { ...a, on: !a.on } : a
      ),
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Floor plan grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gridTemplateRows: 'auto auto',
        gap: 6,
        backgroundColor: C.wall,
        borderRadius: 18,
        padding: 6,
      }}>
        {ROOM_LAYOUTS.map(layout => {
          const room = roomMap[layout.id]
          if (!room) return null
          const occupied = room.occupied === true
          const isSelected = selected === layout.id

          const gridPlacement =
            layout.id === 'living-room' ? { gridColumn: 1, gridRow: 1 }
              : layout.id === 'bedroom' ? { gridColumn: 1, gridRow: 2 }
                : { gridColumn: 2, gridRow: '1 / 3' }

          return (
            <motion.div
              key={layout.id}
              onClick={() => setSelected(p => p === layout.id ? null : layout.id)}
              style={{
                ...gridPlacement,
                aspectRatio: layout.id === 'kitchen' ? undefined : '3/2',
                minHeight: layout.id === 'kitchen' ? 0 : undefined,
                position: 'relative',
                borderRadius: 12,
                cursor: 'pointer',
                outline: isSelected ? `2px solid ${C.textPri}` : '2px solid transparent',
                outlineOffset: -2,
                transition: 'outline 0.2s',
                backgroundImage: `url(${layout.bg})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                overflow: 'hidden',
              }}
            >
              {/* Photo overlay */}
              <div style={{
                position: 'absolute', inset: 0,
                backgroundColor: occupied ? 'rgba(0,0,0,0.05)' : 'rgba(0,0,0,0.40)',
                transition: 'background-color 0.3s',
                pointerEvents: 'none',
              }} />

              {/* Room name */}
              <div style={{
                position: 'absolute', top: 8, left: 9,
                fontSize: 9, fontWeight: 800,
                color: 'rgba(255,255,255,0.92)',
                letterSpacing: '0.6px', textTransform: 'uppercase',
                backgroundColor: 'rgba(255,255,255,0.14)',
                backdropFilter: 'blur(6px)',
                borderRadius: 6, padding: '3px 8px',
                pointerEvents: 'none', zIndex: 1,
              }}>
                {room.name}
              </div>

              {/* Temp/humidity badge */}
              {room.hasDHT && room.temp != null && (
                <div style={{
                  position: 'absolute', top: 8, right: 9,
                  fontSize: 9, fontWeight: 700,
                  color: '#FFB340',
                  backgroundColor: 'rgba(255,255,255,0.14)',
                  backdropFilter: 'blur(6px)',
                  borderRadius: 6, padding: '3px 8px',
                  pointerEvents: 'none', zIndex: 1,
                }}>
                  {room.temp}° · {room.humidity}%
                </div>
              )}

              {/* Appliance markers */}
              {layout.appliances.map(app => {
                const appState = room.appliances.find(a => a.id === app.id)
                return (
                  <div key={app.id} style={{
                    position: 'absolute',
                    left: app.x, top: app.y,
                    transform: 'translate(-50%, -50%)',
                    zIndex: 1,
                  }}>
                    <ApplianceMarker
                      appId={app.id}
                      on={appState?.on ?? false}
                      onClick={() => toggleAppliance(layout.id, app.id)}
                    />
                  </div>
                )
              })}
            </motion.div>
          )
        })}
      </div>


      {/* Hint */}
      <AnimatePresence>
        {!selected && (
          <motion.p
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ fontSize: 12, color: C.textMute, fontWeight: 500, textAlign: 'center', margin: 0 }}
          >
            Click a room to edit its settings
          </motion.p>
        )}
      </AnimatePresence>

      {/* Selected room controls */}
      <AnimatePresence>
        {selRoom && (
          <motion.div
            key={selected}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.25 }}
            style={{
              backgroundColor: C.card, borderRadius: 20,
              padding: '18px 20px',
              boxShadow: '0 1px 12px rgba(0,0,0,0.04)',
              display: 'flex', flexDirection: 'column', gap: 14,
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: C.textPri }}>{selRoom.name}</div>
                <div style={{ fontSize: 11, color: C.textMute, marginTop: 2 }}>{selRoom.pi}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: C.textMute }}>
                  {selRoom.occupied ? 'Occupied' : 'Empty'}
                </span>
                <Toggle
                  on={selRoom.occupied === true}
                  onChange={val => onUpdateRoom(selected, { occupied: val })}
                />
              </div>
            </div>

            {/* Sliders */}
            {selRoom.hasDHT && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <SimSlider
                  label="Temperature" value={selRoom.temp}
                  min={18} max={35} step={0.1} unit="°C"
                  onChange={val => onUpdateRoom(selected, { temp: val })}
                />
                <SimSlider
                  label="Humidity" value={selRoom.humidity}
                  min={30} max={90} step={1} unit="%"
                  onChange={val => onUpdateRoom(selected, { humidity: val })}
                />
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Clock ────────────────────────────────────────────────────────────────────

function useClock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return {
    timeStr: time.toLocaleTimeString('en-SG', { hour: '2-digit', minute: '2-digit' }),
    dateStr: time.toLocaleDateString('en-SG', { weekday: 'long', month: 'long', day: 'numeric' }),
  }
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [rooms, setRooms] = useState(INITIAL_ROOMS)
  const [awayMode, setAwayMode] = useState(false)
  const [roomConfigs, setRoomConfigs] = useState(DEFAULT_ROOM_CONFIGS)
  const { timeStr, dateStr } = useClock()

  // Fetch current per-room configs from Pi 1 on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/config`)
      .then(r => r.json())
      .then(data => setRoomConfigs(prev => ({ ...prev, ...data })))
      .catch(() => { })
  }, [])

  // Debounced POST whenever any room config changes
  const updateRoomConfig = (roomId, newConfig) => {
    setRoomConfigs(prev => ({ ...prev, [roomId]: newConfig }))
    clearTimeout(updateRoomConfig._timer)
    updateRoomConfig._timer = setTimeout(() => {
      fetch(`${API_BASE}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId, ...newConfig }),
      }).catch(() => { })
    }, 600)
  }

  const occupied = rooms.filter(r => r.occupied === true).length

  const toggleAppliance = (roomId, applianceId, val) =>
    setRooms(prev => prev.map(room =>
      room.id !== roomId ? room : {
        ...room,
        appliances: room.appliances.map(a =>
          a.id === applianceId ? { ...a, on: val } : a
        ),
      }
    ))

  const updateRoom = (roomId, patch) =>
    setRooms(prev => prev.map(room =>
      room.id !== roomId ? room : { ...room, ...patch }
    ))

  return (
    <div style={{ minHeight: '100vh', backgroundColor: C.bg, fontFamily: '"Plus Jakarta Sans", sans-serif' }}>
      <div className="app-container">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32 }}
        >
          <div>
            <div style={{ fontSize: 30, fontWeight: 800, color: C.textPri, letterSpacing: '-0.5px' }}>
              Smart Home
            </div>
            <div style={{ fontSize: 13, color: C.textSec, marginTop: 5, fontWeight: 500 }}>
              {dateStr}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12 }}>
            <div style={{ fontSize: 26, fontWeight: 700, color: C.textPri, letterSpacing: '-0.4px', fontVariantNumeric: 'tabular-nums' }}>
              {timeStr}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <motion.span
                animate={{ color: C.textSec }}
                style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}
              >
                <MoonIcon /> Away
              </motion.span>
              <Toggle on={awayMode} onChange={setAwayMode} />
            </div>
          </div>
        </motion.div>

        {/* Summary pill */}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            backgroundColor: C.card, borderRadius: 999,
            padding: '7px 14px', marginBottom: 24,
            boxShadow: '0 1px 8px rgba(0,0,0,0.05)',
          }}
        >
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            backgroundColor: occupied > 0 && !awayMode ? C.green : C.toggleOff,
          }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: C.textPri }}>
            {occupied} of {rooms.length} rooms occupied
          </span>
        </motion.div>

        {/* Simulator */}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }} style={{ marginBottom: 32 }}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: C.textMute, letterSpacing: '0.6px', textTransform: 'uppercase', marginBottom: 12 }}>
            Simulator
          </div>
          <FloorPlan rooms={rooms} onUpdateRoom={updateRoom} />
        </motion.div>

        {/* Room cards */}
        <div className="room-grid">
          {rooms.map((room, i) => (
            <RoomCard
              key={room.id} room={room} index={i}
              awayMode={awayMode} onToggleAppliance={toggleAppliance}
              config={roomConfigs[room.id]}
              onConfigChange={cfg => updateRoomConfig(room.id, cfg)}
            />
          ))}
        </div>


      </div>
    </div>
  )
}
