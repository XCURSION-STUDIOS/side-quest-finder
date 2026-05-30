import React, { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import XCursionLogo from './XCursionLogo'

const API = 'http://localhost:8000'

const SUPPORTED_SERVICES = [
  'meetup',
  'eventbrite',
  'facebook',
  'instagram',
  'reddit',
  'telegram',
  'strava',
  'classpass',
  'onepa',
  'peatix',
  'humanitix',
  'eventsize',
  'linkedin',
  'tiktok',
  'youtube',
]

const ACTIVE_SOURCE_IDS = ['meetup', 'eventbrite', 'reddit', 'peatix', 'timeout']
const SEARCH_POSTURE_OPTIONS = [
  { value: 'recent_public', label: 'recent public pages' },
  { value: 'official_first', label: 'official organisers first' },
  { value: 'community_wide', label: 'community wide net' },
]
const QUALITY_FILTER_OPTIONS = [
  { value: 'strict', label: 'strict' },
  { value: 'balanced', label: 'balanced' },
  { value: 'exploratory', label: 'exploratory' },
]

const SUGGESTED_INTERESTS = [
  'climbing',
  'football',
  'running clubs',
  'volunteering',
  'board games',
  'church groups',
  'language exchange',
  'art workshops',
  'founder meetups',
  'book clubs',
  'martial arts',
  'photography walks',
]

const FOCUS_OPTIONS = [
  { id: 'make_friends', title: 'make friends', detail: 'Prefer recurring groups, socials, beginner-friendly clubs, and community meetups.' },
  { id: 'dating', title: 'find a partner', detail: 'Include mixers, singles events, social dance, and low-pressure group settings.' },
  { id: 'fitness', title: 'get fit', detail: 'Prioritise sports, run crews, classes, hikes, martial arts, and active communities.' },
  { id: 'use_time', title: 'use up time', detail: 'Look for interesting one-offs, workshops, talks, weekend plans, and low-commitment events.' },
  { id: 'give_back', title: 'give back', detail: 'Surface charities, volunteering, mutual aid, and community service opportunities.' },
  { id: 'learn', title: 'learn something', detail: 'Find classes, lessons, workshops, practice groups, and beginner-friendly skill sessions.' },
]

const NAV_ITEMS = [
  { id: 'discover', icon: '>', label: 'discover' },
  { id: 'briefing', icon: '!', label: 'briefing' },
  { id: 'shortlist', icon: '$', label: 'shortlist' },
  { id: 'focus', icon: '@', label: 'focus' },
  { id: 'personalise', icon: '+', label: 'personalise' },
  { id: 'sources', icon: '#', label: 'sources' },
  { id: 'settings', icon: '*', label: 'settings' },
]

const REGION_CODES = [
  'AF','AX','AL','DZ','AS','AD','AO','AI','AQ','AG','AR','AM','AW','AU','AT','AZ',
  'BS','BH','BD','BB','BY','BE','BZ','BJ','BM','BT','BO','BQ','BA','BW','BV','BR',
  'IO','BN','BG','BF','BI','CV','KH','CM','CA','KY','CF','TD','CL','CN','CX','CC',
  'CO','KM','CG','CD','CK','CR','CI','HR','CU','CW','CY','CZ','DK','DJ','DM','DO',
  'EC','EG','SV','GQ','ER','EE','SZ','ET','FK','FO','FJ','FI','FR','GF','PF','TF',
  'GA','GM','GE','DE','GH','GI','GR','GL','GD','GP','GU','GT','GG','GN','GW','GY',
  'HT','HM','VA','HN','HK','HU','IS','IN','ID','IR','IQ','IE','IM','IL','IT','JM',
  'JP','JE','JO','KZ','KE','KI','KP','KR','KW','KG','LA','LV','LB','LS','LR','LY',
  'LI','LT','LU','MO','MG','MW','MY','MV','ML','MT','MH','MQ','MR','MU','YT','MX',
  'FM','MD','MC','MN','ME','MS','MA','MZ','MM','NA','NR','NP','NL','NC','NZ','NI',
  'NE','NG','NU','NF','MK','MP','NO','OM','PK','PW','PS','PA','PG','PY','PE','PH',
  'PN','PL','PT','PR','QA','RE','RO','RU','RW','BL','SH','KN','LC','MF','PM','VC',
  'WS','SM','ST','SA','SN','RS','SC','SL','SG','SX','SK','SI','SB','SO','ZA','GS',
  'SS','ES','LK','SD','SR','SJ','SE','CH','SY','TW','TJ','TZ','TH','TL','TG','TK',
  'TO','TT','TN','TR','TM','TC','TV','UG','UA','AE','GB','US','UM','UY','UZ','VU',
  'VE','VN','VG','VI','WF','EH','YE','ZM','ZW',
]

const COUNTRY_OPTIONS = (() => {
  const names = typeof Intl !== 'undefined' && Intl.DisplayNames
    ? new Intl.DisplayNames(['en'], { type: 'region' })
    : null

  return REGION_CODES
    .map(code => ({ code, name: names ? names.of(code) : code }))
    .sort((a, b) => a.name.localeCompare(b.name))
})()

function App(){
  const [activePage, setActivePage] = useState('discover')
  const [interests, setInterests] = useState([])
  const [focus, setFocus] = useState(['make_friends'])
  const [input, setInput] = useState('')
  const [items, setItems] = useState(null)
  const [shortlistItems, setShortlistItems] = useState([])
  const [showServices, setShowServices] = useState(false)
  const [settings, setSettings] = useState({
    dailySummary: true,
    maxFinds: 10,
    locationFocus: 'SG',
    discoveryMode: 'balanced',
    enabledSources: ACTIVE_SOURCE_IDS,
    searchPosture: 'recent_public',
    qualityFilter: 'strict',
    testingMode: false,
  })

  useEffect(() => {
    try {
      const savedSettings = window.localStorage.getItem('xcursion-settings')
      if(savedSettings){
        const parsedSettings = JSON.parse(savedSettings)
        setSettings(current => ({
          ...current,
          ...parsedSettings,
          locationFocus: normalizeCountryValue(parsedSettings.locationFocus || current.locationFocus),
        }))
      }
    } catch {
      window.localStorage.removeItem('xcursion-settings')
    }

    fetch(`${API}/preferences`)
      .then(response => response.json())
      .then(data => {
        setInterests(data.interests || [])
        setFocus(data.focus && data.focus.length ? data.focus : ['make_friends'])
        if(data.settings){
          setSettings(current => ({
            ...current,
            ...data.settings,
            locationFocus: normalizeCountryValue(data.settings.locationFocus || current.locationFocus),
          }))
        }
      })
      .catch(() => setInterests([]))

    fetchSummary()
    fetchShortlist()
  }, [])

  useEffect(() => {
    window.localStorage.setItem('xcursion-settings', JSON.stringify(settings))
  }, [settings])

  function addInterest(value = input){
    const cleanInput = value.trim()
    if(!cleanInput) return
    if(interests.some(interest => interest.toLowerCase() === cleanInput.toLowerCase())){
      setInput('')
      setActivePage('personalise')
      return
    }

    const next = [...interests, cleanInput]
    setInterests(next)
    setInput('')
    saveProfile({ interests: next })
    setActivePage('personalise')
  }

  function removeInterest(index){
    const next = interests.filter((_, itemIndex) => itemIndex !== index)
    setInterests(next)
    saveProfile({ interests: next })
  }

  function saveProfile(overrides = {}){
    const nextInterests = overrides.interests || interests
    const nextFocus = overrides.focus || focus
    const nextSettings = overrides.settings || settings

    return fetch(`${API}/preferences`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        interests: nextInterests,
        focus: nextFocus,
        settings: nextSettings,
      }),
    }).catch(() => {})
  }

  function fetchSummary(){
    fetch(`${API}/summary`)
      .then(response => response.json())
      .then(data => setItems(data.items || []))
      .catch(() => setItems([]))
  }

  function fetchShortlist(){
    fetch(`${API}/shortlist`)
      .then(response => response.json())
      .then(data => setShortlistItems(data.items || []))
      .catch(() => setShortlistItems([]))
  }

  function runDiscovery(){
    fetch(`${API}/discovery/run`, { method: 'POST' })
      .then(response => response.json())
      .then(data => {
        setItems(data.items || [])
        fetchShortlist()
      })
      .catch(() => setItems([]))
  }

  function patchItem(itemId, payload){
    if(itemId < 0){
      const applyDemoUpdate = item => item.id === itemId ? { ...item, ...payload } : item
      setItems(current => current ? current.map(applyDemoUpdate) : current)
      setShortlistItems(current => {
        const updatedItems = (items || []).map(applyDemoUpdate)
        return updatedItems.filter(item => item.shortlisted)
      })
      return
    }

    fetch(`${API}/items/${itemId}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(response => response.json())
      .then(updated => {
        const applyUpdate = item => item.id === itemId ? { ...item, ...updated } : item
        setItems(current => current ? current.map(applyUpdate) : current)
        fetchShortlist()
      })
      .catch(() => {})
  }

  function updateSetting(key, value){
    setSettings(current => {
      const next = { ...current, [key]: value }
      saveProfile({ settings: next }).then(() => {
        if(['testingMode', 'maxFinds', 'dailySummary'].includes(key)){
          fetchSummary()
          fetchShortlist()
        }
      })
      return next
    })
  }

  function toggleFocus(focusId){
    setFocus(current => {
      const next = current.includes(focusId)
        ? current.filter(item => item !== focusId)
        : [...current, focusId]
      const safeNext = next.length ? next : ['make_friends']
      saveProfile({ focus: safeNext })
      return safeNext
    })
  }

  return (
    <>
      <aside className="left-toolbar" aria-label="Primary navigation">
        <button className="rail-brand" onClick={() => setActivePage('discover')} aria-label="XCursion Studios home">
          <XCursionLogo size={34} staticMode />
        </button>

        <div className="toolbar-nav">
          {NAV_ITEMS.map(item => (
            <button
              className={`toolbar-item ${activePage === item.id ? 'active' : ''}`}
              key={item.id}
              onClick={() => setActivePage(item.id)}
            >
              <span className="tb-btn" aria-hidden="true">{item.icon}</span>
              <span className="toolbar-label">{item.label}</span>
            </button>
          ))}
        </div>
      </aside>

      {activePage !== 'sources' && (
        <ServicesPopover showServices={showServices} setShowServices={setShowServices} />
      )}

      <div className="center-root">
        <AnimatePresence mode="wait">
          {activePage === 'discover' && (
            <DiscoverPage
              key="discover"
              items={items}
              openBriefing={() => setActivePage('briefing')}
            />
          )}
          {activePage === 'briefing' && (
            <BriefingPage
              key="briefing"
              items={items}
              runDiscovery={runDiscovery}
              settings={settings}
              patchItem={patchItem}
            />
          )}
          {activePage === 'shortlist' && (
            <ShortlistPage
              key="shortlist"
              items={shortlistItems}
              patchItem={patchItem}
            />
          )}
          {activePage === 'personalise' && (
            <PersonalisePage
              key="personalise"
              interests={interests}
              addInterest={addInterest}
              removeInterest={removeInterest}
              input={input}
              setInput={setInput}
            />
          )}
          {activePage === 'focus' && (
            <FocusPage
              key="focus"
              focus={focus}
              toggleFocus={toggleFocus}
            />
          )}
          {activePage === 'sources' && (
            <SourcesPage key="sources" settings={settings} updateSetting={updateSetting} />
          )}
          {activePage === 'settings' && (
            <SettingsPage key="settings" interests={interests} settings={settings} updateSetting={updateSetting} />
          )}
        </AnimatePresence>
      </div>

      <motion.div
        className="studio-credit"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.55, duration: 0.45 }}
      >
        an <strong>xcursion studios</strong> app
      </motion.div>
    </>
  )
}

function normalizeCountryValue(value){
  if(!value) return 'SG'
  const upperValue = String(value).toUpperCase()
  if(REGION_CODES.includes(upperValue)) return upperValue

  const matchedCountry = COUNTRY_OPTIONS.find(country => (
    country.name.toLowerCase() === String(value).toLowerCase()
  ))

  return matchedCountry ? matchedCountry.code : 'SG'
}

function PageShell({ children, className = '' }){
  return (
    <motion.main
      className={`center-card page-shell ${className}`}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
    >
      {children}
    </motion.main>
  )
}

function ServicesPopover({ showServices, setShowServices }){
  return (
    <div className="services-popover">
      <motion.div
        className="services-inner"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12, duration: 0.36, ease: 'easeOut' }}
      >
        <div className="services-title">
          <button
            className="services-toggle"
            aria-label={showServices ? 'Hide supported services' : 'Show supported services'}
            aria-expanded={showServices}
            onClick={() => setShowServices(current => !current)}
          >
            {showServices ? 'x' : '+'}
          </button>
          <span>supported services</span>
        </div>
        <AnimatePresence>
          {showServices && <ServicesCard />}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

function ServicesCard({ expanded = false }){
  return (
    <motion.div
      className={`services-card ${expanded ? 'expanded' : ''}`}
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.98 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      <div className="service-chips" aria-label="Supported hobby search services">
        {SUPPORTED_SERVICES.map(service => (
          <span className="service-chip" key={service}>{service}</span>
        ))}
      </div>
      <p>
        support for a service means technical compatibility for discovery,
        not affiliation, endorsement, or partnership.
      </p>
    </motion.div>
  )
}

function DiscoverPage({ items, openBriefing }){
  return (
    <PageShell className="discover-page">
      <div className="logo-wrap">
        <XCursionLogo size={112} />
      </div>

      <div className="home-title" aria-label="XCursion finds your next side quest">
        <span className="title-kicker">xcursion agent</span>
        <h1 data-text="find your next side quest">find your next side quest</h1>
      </div>

      <motion.section
        className="home-brief"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.14, duration: 0.38 }}
      >
        <div className="home-brief-module">
          <div className="small-title">Today's Summary</div>
          <div className="home-brief-list">
            {items && items.length > 0 ? (
              items.slice(0, 3).map((item, index) => (
                <a key={index} className="home-brief-item" href={item.link || '#'} target="_blank" rel="noreferrer">
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <strong>{item.title}</strong>
                </a>
              ))
            ) : (
              <div className="home-empty">No new updates</div>
            )}
          </div>
        </div>
      </motion.section>
    </PageShell>
  )
}

function BriefingPage({ items, runDiscovery, settings, patchItem }){
  const visibleLimit = Number(settings.maxFinds) || 10

  return (
    <PageShell className="wide-page">
      <PageHeader
        title="daily briefing"
        description="A focused feed of fresh clubs, meetups, hobby groups, and community openings found by the agent."
      />
      <div className="briefing-toolbar">
        <span>{settings.dailySummary ? `limit: ${visibleLimit} discoveries / day` : 'daily summary paused'}</span>
        <button className="subtle-command" onClick={runDiscovery}>run agent manually</button>
      </div>
      <div className="result-list">
        {items && items.length > 0 ? (
          items.slice(0, visibleLimit).map((item, index) => (
            <ActivityRow
              item={item}
              index={index}
              key={item.id || `${item.title}-${index}`}
              patchItem={patchItem}
            />
          ))
        ) : (
          <div className="empty-state">
            <span>no new updates</span>
            <p>The agent has not found anything new today. It will keep watching your sources.</p>
          </div>
        )}
      </div>
    </PageShell>
  )
}

function ShortlistPage({ items, patchItem }){
  return (
    <PageShell className="wide-page">
      <PageHeader
        title="shortlist"
        description="Saved activities and communities you might want to revisit, compare, or actually go to."
      />
      <div className="result-list">
        {items && items.length > 0 ? items.map((item, index) => (
          <ActivityRow
            item={item}
            index={index}
            key={item.id || `${item.title}-${index}`}
            patchItem={patchItem}
          />
        )) : (
          <div className="empty-state">
            <span>nothing shortlisted yet</span>
            <p>Save recommendations from the briefing and they will collect here.</p>
          </div>
        )}
      </div>
    </PageShell>
  )
}

function ActivityRow({ item, index, patchItem }){
  const feedbackOptions = ['good', 'neutral', 'bad']
  const host = getLinkHost(item.link)

  return (
    <div className="result-row activity-row">
      <a className="activity-main" href={item.link || '#'} target="_blank" rel="noreferrer">
        <span className="row-index">{String(index + 1).padStart(2, '0')}</span>
        <span>
          <strong>{item.title}</strong>
          <small>
            <span className="source-badge">{item.source || 'source'}</span>
            {[item.location, item.activity_when, host].filter(Boolean).join(' / ')}
          </small>
        </span>
      </a>
      <div className="activity-actions">
        <button
          className={`shortlist-button icon-only ${item.shortlisted ? 'active' : ''}`}
          onClick={() => patchItem(item.id, { shortlisted: !item.shortlisted })}
          disabled={!item.id}
          aria-label={item.shortlisted ? 'Remove from shortlist' : 'Add to shortlist'}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 4h10v16l-5-3-5 3V4z" />
          </svg>
        </button>
        <div className="rating-controls" aria-label="Suggestion feedback">
          {feedbackOptions.map(option => (
            <button
              className={`${option} ${item.feedback === option ? 'active' : ''}`}
              key={option}
              onClick={() => patchItem(item.id, { feedback: item.feedback === option ? null : option })}
              disabled={!item.id}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function getLinkHost(link){
  if(!link) return null
  try {
    return new URL(link).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

function FocusPage({ focus, toggleFocus }){
  return (
    <PageShell className="wide-page">
      <PageHeader
        title="focus"
        description="Tell the discovery agent what kind of life outcome you want from the activities it finds."
      />
      <div className="focus-grid">
        {FOCUS_OPTIONS.map(option => (
          <button
            className={`focus-card ${focus.includes(option.id) ? 'selected' : ''}`}
            key={option.id}
            onClick={() => toggleFocus(option.id)}
          >
            <span>{option.title}</span>
            <p>{option.detail}</p>
          </button>
        ))}
      </div>
    </PageShell>
  )
}

function PersonalisePage({ interests, addInterest, removeInterest, input, setInput }){
  return (
    <PageShell className="wide-page">
      <PageHeader
        title="personalise"
        description="Tune the agent toward the sports, communities, faith groups, charities, and meetups you actually care about."
      />
      <div className="form-row">
        <input
          className="panel-input"
          placeholder="Add an interest, e.g. climbing, volunteering, book clubs"
          value={input}
          onChange={event => setInput(event.target.value)}
          onKeyDown={event => {
            if(event.key === 'Enter') addInterest()
          }}
        />
        <button className="panel-button" onClick={() => addInterest()}>add</button>
      </div>

      <div className="section-block">
        <div className="small-title">Your interests</div>
        <div className="chips-inline large">
          {interests.length > 0 ? interests.map((interest, index) => (
            <motion.span
              key={`${interest}-${index}`}
              className="chip"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
            >
              {interest}
              <button className="chip-x" onClick={() => removeInterest(index)}>x</button>
            </motion.span>
          )) : (
            <span className="muted-line">No interests saved yet.</span>
          )}
        </div>
      </div>

      <div className="section-block">
        <div className="small-title">Quick seeds</div>
        <div className="seed-grid">
          {SUGGESTED_INTERESTS.map(seed => (
            <button className="seed-button" key={seed} onClick={() => addInterest(seed)}>
              {seed}
            </button>
          ))}
        </div>
      </div>
    </PageShell>
  )
}

function SourcesPage({ settings, updateSetting }){
  const enabledSources = Array.isArray(settings.enabledSources) && settings.enabledSources.length
    ? settings.enabledSources
    : ACTIVE_SOURCE_IDS

  function toggleSource(source){
    const next = enabledSources.includes(source)
      ? enabledSources.filter(item => item !== source)
      : [...enabledSources, source]
    updateSetting('enabledSources', next.length ? next : [source])
  }

  return (
    <PageShell className="wide-page sources-page">
      <PageHeader
        title="sources"
        description="Places the agent can watch for public events, clubs, hobby groups, and community signals around Singapore."
      />
      <SourceSelector enabledSources={enabledSources} toggleSource={toggleSource} />
      <div className="source-notes">
        <div className="policy-box">
          <div className="small-title">search posture</div>
          <CustomDropdown
            value={settings.searchPosture}
            options={SEARCH_POSTURE_OPTIONS}
            onChange={value => updateSetting('searchPosture', value)}
          />
        </div>
        <div className="policy-box">
          <div className="small-title">quality filter</div>
          <CustomDropdown
            value={settings.qualityFilter}
            options={QUALITY_FILTER_OPTIONS}
            onChange={value => updateSetting('qualityFilter', value)}
          />
        </div>
      </div>
    </PageShell>
  )
}

function SourceSelector({ enabledSources, toggleSource }){
  return (
    <motion.div
      className="services-card expanded source-selector"
      initial={{ opacity: 0, y: -8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      <div className="service-chips selectable" aria-label="Selectable discovery sources">
        {SUPPORTED_SERVICES.map(service => {
          const active = enabledSources.includes(service)
          const implemented = ACTIVE_SOURCE_IDS.includes(service)
          return (
            <button
              className={`service-chip source-chip ${active ? 'active' : ''}`}
              key={service}
              onClick={() => implemented && toggleSource(service)}
              disabled={!implemented}
              title={implemented ? 'Toggle this source' : 'Connector planned'}
            >
              {service}
            </button>
          )
        })}
      </div>
      <p>
        enabled chips are searched by the agent. dimmed chips are planned connectors and will become selectable once their integration is added.
      </p>
    </motion.div>
  )
}

function SettingsPage({ interests, settings, updateSetting }){
  return (
    <PageShell className="wide-page">
      <PageHeader
        title="settings"
        description="Control how assertive the discovery agent should be when collecting and summarising opportunities."
      />
      <div className="settings-grid">
        <SettingLine label="daily summary">
          <button
            className={`toggle-control ${settings.dailySummary ? 'on' : ''}`}
            onClick={() => updateSetting('dailySummary', !settings.dailySummary)}
          >
            {settings.dailySummary ? 'enabled' : 'paused'}
          </button>
        </SettingLine>
        <SettingLine label="maximum finds">
          <input
            className="setting-input number"
            type="number"
            min="1"
            max="25"
            value={settings.maxFinds}
            onChange={event => updateSetting('maxFinds', event.target.value)}
          />
          <span className="setting-suffix">per day</span>
        </SettingLine>
        <SettingLine label="location focus">
          <CountryDropdown
            value={settings.locationFocus}
            onChange={value => updateSetting('locationFocus', value)}
          />
        </SettingLine>
        <SettingLine label="discovery mode">
          <select
            className="setting-input select"
            value={settings.discoveryMode}
            onChange={event => updateSetting('discoveryMode', event.target.value)}
          >
            <option value="precise">precise</option>
            <option value="balanced">balanced</option>
            <option value="wide">wide net</option>
          </select>
        </SettingLine>
        <SettingLine label="interest signals" value={`${interests.length} saved`} />
        <SettingLine label="testing mode">
          <button
            className={`toggle-control subtle ${settings.testingMode ? 'on' : ''}`}
            onClick={() => updateSetting('testingMode', !settings.testingMode)}
          >
            {settings.testingMode ? 'demo on' : 'demo off'}
          </button>
        </SettingLine>
      </div>
    </PageShell>
  )
}

function CountryDropdown({ value, onChange }){
  return (
    <CustomDropdown
      className="country-dropdown"
      value={value}
      options={COUNTRY_OPTIONS.map(country => ({ value: country.code, label: country.name }))}
      onChange={onChange}
    />
  )
}

function CustomDropdown({ value, options, onChange, className = '' }){
  const [open, setOpen] = useState(false)
  const selectedOption = options.find(option => option.value === value) || options[0]

  return (
    <div className={`custom-dropdown ${className}`}>
      <button
        className={`custom-trigger ${open ? 'open' : ''}`}
        onClick={() => setOpen(current => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span>{selectedOption.label}</span>
        <span aria-hidden="true">v</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="custom-menu"
            role="listbox"
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
          >
            {options.map(option => (
              <button
                className={`custom-option ${option.value === value ? 'selected' : ''}`}
                key={option.value}
                role="option"
                aria-selected={option.value === value}
                onClick={() => {
                  onChange(option.value)
                  setOpen(false)
                }}
              >
                {option.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function PageHeader({ title, description }){
  return (
    <header className="page-header">
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  )
}

function SettingLine({ label, value, children }){
  return (
    <div className="setting-line">
      <span>{label}</span>
      <div className="setting-control">
        {children || <strong>{value}</strong>}
      </div>
    </div>
  )
}

export default App
