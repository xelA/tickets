function unix_to_timestamp(e) {
  if (!e) return
  let unix = parseInt(e.innerText)
  let date = new Date(unix * 1000)
  let months_arr = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ]

  let day = date.getDate()
  let month = months_arr[date.getMonth()]
  let year = date.getFullYear()

  let hours = ("0" + date.getHours()).slice(-2)
  let minutes = ("0" + date.getMinutes()).slice(-2)
  let seconds = ("0" + date.getSeconds()).slice(-2)

  const converted_date = `${day}. ${month} ${year}, ${hours}:${minutes}`

  e.innerText = converted_date

  return converted_date
}

// Clicking these inside a message does its own thing (enlarge, play, open, reveal), not jump to the message
const NO_JUMP = "img[data-enlargable], video, audio, a, .spoiler, .spoiler-media, .d-button, .d-select"

function scroll_to(get_id, event) {
  if (event && event.target.closest(NO_JUMP)) return
  let id = get_id.replace("#", "")
  const el = document.getElementById(id)
  if (!el) return
  const prev = document.querySelector('.targetted')
  if (prev) prev.classList.remove('targetted')
  el.classList.add('targetted')
  el.scrollIntoView({behavior: 'smooth', inline: "nearest"})
  history.pushState(null, null, `#${id}`)
}

function toggle_theme() {
  const root = document.documentElement
  const theme = root.classList.contains("theme-light") ? "dark" : "light"
  root.className = `theme-${theme}`
  try { localStorage.setItem("theme", theme) } catch (e) {}
}

function toggle_msg(type, target) {
  let button = document.getElementById(type).checked
  let msg_elements = document.getElementsByClassName(target)
  for (var i = 0; i < msg_elements.length; i++) {
    if (button === true) {
      msg_elements[i].classList.remove("hide")
    } else {
      msg_elements[i].classList.add("hide")
    }
  }
}

// Spoilers (text and media) are revealed on the first click, that click does nothing else
document.addEventListener("click", e => {
  const spoiler = e.target.closest(".spoiler:not(.revealed), .spoiler-media:not(.revealed)")
  if (!spoiler) return
  spoiler.classList.add("revealed")
  e.preventDefault()
  e.stopPropagation()
}, true)

// Home page upload: picking or dropping a file uploads it straight away
function setup_dropzone() {
  const form = document.getElementById("upload_form")
  if (!form) return
  const input = form.querySelector("input[type=file]")
  const text = form.querySelector(".dropzone-text")

  const upload = () => {
    if (!input.files.length) return
    text.textContent = `Uploading ${input.files[0].name}...`
    form.classList.add("uploading")
    form.submit()
  }

  // Coming back with the browser's back button restores the page as it was when it left
  const idle_text = text.textContent
  window.addEventListener("pageshow", () => {
    form.classList.remove("uploading")
    text.textContent = idle_text
    input.value = ""
  })

  input.addEventListener("change", upload)
  form.addEventListener("dragover", e => { e.preventDefault(); form.classList.add("dragging") })
  form.addEventListener("dragleave", () => form.classList.remove("dragging"))
  form.addEventListener("drop", e => {
    e.preventDefault()
    form.classList.remove("dragging")
    if (!e.dataTransfer.files.length) return
    input.files = e.dataTransfer.files
    upload()
  })
}

window.onload = function() {
  setup_dropzone()

  // Make all timestamps
  unix_to_timestamp(document.getElementById("expire_date"))
  unix_to_timestamp(document.getElementById("created_at"))

  // Enlarge images
  const modal = document.getElementById('modal')
  if (!modal) return

  function openModal(type) {
    modal.querySelector(`#${type}`).style.display = null
    modal.classList.add('opened')
  }

  function closeModal() {
    modal.classList.remove('opened')
    modal.classList.add('closing')
    setTimeout(() => {
      modal.classList.remove('closing')
      modal.querySelectorAll('div').forEach(el => (el.style.display = 'none'))
    }, 200)
  }

  modal.addEventListener('click', closeModal)

  let enlarge = document.getElementById('enlarge')
  enlarge.querySelector('img').addEventListener('click', e => e.stopPropagation())
  document.querySelectorAll('[data-enlargable]').forEach(el => {
    el.addEventListener('click', () => {
      enlarge.querySelector('a').href = el.src
      let target_image = enlarge.querySelector('img')
      target_image.src = el.src
      target_image.style.maxWidth = window.innerWidth - 200
      target_image.style.maxHeight = window.innerHeight - 200
      openModal('enlarge')
    })
  })

  // Scroll if target
  if (location.hash) { scroll_to(location.hash) }
}
