export const dynamic = 'force-dynamic'

import { prisma } from '@/lib/prisma'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  try {
    // Always return all subcategories with their category information
    const allSubcategories = await prisma.occupationSubCategory.findMany({
      select: {
        id: true,
        name: true,
        annual_salary: true,
        typical_years_of_school: true,
        category_id: true,
        category: {
          select: {
            id: true,
            name: true,
          }
        }
      },
      orderBy: {
        name: 'asc',
      },
    })
    
    return NextResponse.json(allSubcategories)
  } catch (error) {
    console.error('Error fetching subcategories:', error)
    return NextResponse.json({ error: 'Failed to fetch subcategories' }, { status: 500 })
  }
} 