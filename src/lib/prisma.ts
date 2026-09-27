import { Prisma, PrismaClient } from '@prisma/client'

const MAX_RETRIES = 5
const BASE_DELAY_MS = 500

function isRetryableError(error: unknown): boolean {
  if (error instanceof Prisma.PrismaClientInitializationError) return true
  if (error instanceof Prisma.PrismaClientKnownRequestError) {
    // P1001: Can't reach database server
    // P1002: Database server timed out
    // P1008: Operations timed out
    // P1017: Server has closed the connection
    if (['P1001', 'P1002', 'P1008', 'P1017'].includes(error.code)) return true
  }
  if (error instanceof Error) {
    const message = error.message.toLowerCase()
    if (
      message.includes('connection refused') ||
      message.includes('connection reset') ||
      message.includes('connect timeout') ||
      message.includes('econnrefused') ||
      message.includes('econnreset') ||
      message.includes('etimedout') ||
      message.includes('socket hang up')
    )
      return true
  }
  return false
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function createPrismaClient(): PrismaClient {
  const client = new PrismaClient()

  return client.$extends({
    query: {
      async $allOperations({ args, query }) {
        let lastError: unknown
        for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
          try {
            return await query(args)
          } catch (error) {
            lastError = error
            if (!isRetryableError(error) || attempt === MAX_RETRIES - 1) throw error
            const delay = BASE_DELAY_MS * Math.pow(2, attempt)
            const jitter = delay * 0.2 * Math.random()
            console.warn(
              `[prisma] Query failed (attempt ${attempt + 1}/${MAX_RETRIES}), retrying in ${Math.round(delay + jitter)}ms...`
            )
            await sleep(delay + jitter)
          }
        }
        throw lastError
      },
    },
  }) as unknown as PrismaClient
}

const globalForPrisma = global as unknown as {
  prisma: PrismaClient | undefined
}

export const prisma = globalForPrisma.prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma
