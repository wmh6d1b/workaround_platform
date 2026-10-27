<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ modelValue: string; label: string; placeholder: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const editor = ref<HTMLElement>()
const color = ref('#315efb')
let savedRange: Range | null = null

function sync(value: string) {
  if (editor.value && editor.value.innerHTML !== value) editor.value.innerHTML = value
}
onMounted(() => sync(props.modelValue))
watch(() => props.modelValue, value => nextTick(() => sync(value)))
function update() { emit('update:modelValue', editor.value?.innerHTML || '') }
function rememberSelection() {
  const selection = window.getSelection()
  if (selection?.rangeCount && editor.value?.contains(selection.anchorNode)) savedRange = selection.getRangeAt(0).cloneRange()
}
function restoreSelection() {
  const element = editor.value!
  element.focus()
  const selection = window.getSelection()!
  const range = savedRange && element.contains(savedRange.commonAncestorContainer) ? savedRange : null
  if (range) { selection.removeAllRanges(); selection.addRange(range) }
  else if (!selection.rangeCount || !element.contains(selection.anchorNode)) {
    const fallback = document.createRange(); fallback.selectNodeContents(element); fallback.collapse(false)
    selection.removeAllRanges(); selection.addRange(fallback)
  }
  return selection.getRangeAt(0)
}
function format(command: string, value?: string) {
  restoreSelection(); document.execCommand(command, false, value); update(); rememberSelection()
}
function insertImage(source: string) {
  const range = restoreSelection(); const image = document.createElement('img')
  image.src = source; image.alt = '粘贴图片'; range.deleteContents(); range.insertNode(image)
  range.setStartAfter(image); range.collapse(true)
  const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range)
  savedRange = range.cloneRange(); update()
}
function paste(event: ClipboardEvent) {
  if (props.disabled) return
  event.preventDefault(); rememberSelection()
  const image = [...(event.clipboardData?.items || [])].find(item => item.type.startsWith('image/'))?.getAsFile()
  if (!image) {
    restoreSelection(); document.execCommand('insertText', false, event.clipboardData?.getData('text/plain') || ''); update(); return
  }
  if (image.size > 5 * 1024 * 1024) return ElMessage.warning('粘贴图片不能超过 5 MB')
  const reader = new FileReader(); reader.onload = () => insertImage(String(reader.result)); reader.readAsDataURL(image)
}
</script>

<template>
  <div class="state-note-editor">
    <label>{{ label }}</label>
    <div v-if="!disabled" class="editor-toolbar"><button type="button" title="加粗" @mousedown.prevent @click="format('bold')"><b>B</b></button><button type="button" title="斜体" @mousedown.prevent @click="format('italic')"><i>I</i></button><button type="button" title="下划线" @mousedown.prevent @click="format('underline')"><u>U</u></button><span /><label title="字体颜色"><input v-model="color" type="color" @change="format('foreColor',color)" />字体颜色</label></div>
    <div ref="editor" class="rich-editor" :class="{readonly:disabled}" :contenteditable="disabled ? 'false' : 'true'" :data-placeholder="placeholder" @input="update" @paste="paste" @keyup="rememberSelection" @mouseup="rememberSelection" />
    <div class="editor-footer"><span>支持文字格式、字体颜色和粘贴图片，单张图片不超过 5 MB</span><small>{{ disabled ? '当前状态只读' : '说明随状态流转提交' }}</small></div>
  </div>
</template>

<style scoped>
.state-note-editor { border-top:1px dashed #e0e5ec; padding-top:13px; margin-top:4px; }.state-note-editor>label { display:block; font-size:10px; color:#667085; margin-bottom:7px; }.editor-toolbar { display:flex; align-items:center; gap:4px; border:1px solid #dfe4eb; border-bottom:0; border-radius:7px 7px 0 0; background:#f8f9fb; padding:6px 8px; }.editor-toolbar button { width:27px; height:25px; border:0; border-radius:4px; background:transparent; color:#475467; cursor:pointer; }.editor-toolbar button:hover { background:#e9edf3; }.editor-toolbar>span { flex:1; }.editor-toolbar>label { display:flex; align-items:center; gap:5px; color:#667085; font-size:9px; cursor:pointer; }.editor-toolbar input { width:24px; height:22px; padding:1px; border:0; background:transparent; cursor:pointer; }.rich-editor { min-height:120px; max-height:420px; overflow:auto; border:1px solid #dfe4eb; border-radius:0 0 7px 7px; padding:11px 12px; outline:none; color:#344054; background:#fff; font-size:11px; line-height:1.75; white-space:pre-wrap; }.rich-editor.readonly { border-radius:7px; background:#f8f9fb; }.rich-editor:focus { border-color:#9db3ec; box-shadow:0 0 0 2px #eef2ff; }.rich-editor:empty:before { content:attr(data-placeholder); color:#a0a8b7; pointer-events:none; }.editor-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:9px; }.editor-footer>span,.editor-footer>small { color:#a0a8b7; font-size:9px; }.rich-editor :deep(img) { display:block; max-width:100%; max-height:300px; border-radius:6px; margin:8px 0; }
</style>
