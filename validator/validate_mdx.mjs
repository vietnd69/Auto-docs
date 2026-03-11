// validate_mdx.mjs
import { compile } from '@mdx-js/mdx'
import { readFileSync } from 'fs'
import { createContext, SourceTextModule, SyntheticModule } from 'vm'

const filepath = process.argv[2]

if (!filepath) {
  console.log(JSON.stringify({ errors: ['No filepath provided'] }))
  process.exit(1)
}

/**
 * Tìm dòng chứa identifier bên trong {…} (bare, không nằm trong backtick/code block)
 * Trả về { line, col } (1-indexed) hoặc { line: -1, col: -1 }
 */
function findBareIdentInSource(raw, ident) {
  const lines = raw.split('\n')
  const bracePattern = new RegExp(`\\{[^}\`]*\\b${ident}\\b[^}\`]*\\}`)
  let inCodeBlock = false

  for (let i = 0; i < lines.length; i++) {
    const stripped = lines[i].trim()
    if (stripped.startsWith('```')) {
      inCodeBlock = !inCodeBlock
      continue
    }
    if (inCodeBlock) continue

    const m = lines[i].match(bracePattern)
    if (m) {
      const idx = lines[i].indexOf(m[0])
      // Đếm backtick trước vị trí match — nếu lẻ thì đang nằm trong inline code
      const before = lines[i].substring(0, idx)
      const backtickCount = (before.match(/`/g) || []).length
      if (backtickCount % 2 === 0) {
        return { line: i + 1, col: idx + 1 }
      }
    }
  }
  return { line: -1, col: -1 }
}

async function run() {
  let raw

  try {
    raw = readFileSync(filepath, 'utf-8')
  } catch (e) {
    console.log(JSON.stringify({ errors: [`Cannot read file: ${e.message}`] }))
    process.exit(1)
  }

  const errors = []

  // Phase 1: Compile MDX (parse + transform)
  let compiled
  try {
    compiled = await compile(raw, { format: 'mdx' })
  } catch (e) {
    // Parse lỗi thường có location info
    const loc = e.line && e.column
      ? ` (line ${e.line}, col ${e.column})`
      : ''
    errors.push(`[mdx] ${e.message}${loc}`)
    console.log(JSON.stringify({ errors }))
    return
  }

  // Phase 2: Evaluate compiled ESM output + call MDXContent() to catch ReferenceError
  try {
    const code = String(compiled)
    const context = createContext({
      // Cung cấp console để debug nếu cần
      console: { log: () => {}, error: () => {}, warn: () => {} }
    })

    const mod = new SourceTextModule(code, { context })

    // Link: cung cấp stub modules cho tất cả imports
    await mod.link((specifier) => {
      const stubModule = new SyntheticModule(
        ['default', 'Fragment', 'jsx', 'jsxs', 'jsxDEV', 'useMDXComponents'],
        function () {
          this.setExport('default', () => null)
          this.setExport('Fragment', 'Fragment')
          this.setExport('jsx', (type, props) => props)
          this.setExport('jsxs', (type, props) => props)
          this.setExport('jsxDEV', (type, props) => props)
          this.setExport('useMDXComponents', () => ({}))
        },
        { context }
      )
      return stubModule
    })

    await mod.evaluate()

    // Gọi MDXContent() export để trigger ReferenceError
    const ns = mod.namespace
    if (ns.default && typeof ns.default === 'function') {
      try {
        ns.default({ components: {} })
      } catch (e) {
        throw e  // Re-throw để xử lý ở catch bên ngoài
      }
    }
  } catch (e) {
    const errName = e?.constructor?.name || ''
    if (errName === 'ReferenceError' || e instanceof ReferenceError) {
      const match = e.message.match(/^(\w+) is not defined/)
      const ident = match ? match[1] : '?'
      const loc = findBareIdentInSource(raw, ident)
      errors.push(`[mdx] ReferenceError: ${e.message} (line ${loc.line}, col ${loc.col})`)
    } else if (errName !== 'TypeError') {
      // TypeError thường do stub args — bỏ qua
      // Các lỗi khác thì report
      errors.push(`[mdx] RuntimeError: ${e.message}`)
    }
  }

  console.log(JSON.stringify({ errors }))
}

run()