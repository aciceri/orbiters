import { describe, expect, it } from 'vitest'
import { isLinkedinName, linkedinFieldValue, linkedinProfile } from './linkedin'

const ADA = 'https://www.linkedin.com/in/ada-lovelace'

describe('linkedinProfile', () => {
  it.each([
    'ada-lovelace',
    '  ada-lovelace  ',
    'ada-lovelace/?utm_source=share',
    'linkedin.com/in/ada-lovelace',
    'www.linkedin.com/in/ada-lovelace/',
    'it.linkedin.com/in/ada-lovelace',
    'https://www.linkedin.com/in/ada-lovelace?utm_source=share&utm_medium=member_ios',
    'https://www.linkedin.com/in/ada-lovelace/details/experience/#top',
    'http://linkedin.com/in/ada-lovelace',
  ])('reads %j as the profile', (input) => {
    expect(linkedinProfile(input)).toBe(ADA)
  })

  it('keeps another page on LinkedIn as it is, over https', () => {
    expect(linkedinProfile('http://www.linkedin.com/company/rebase')).toBe(
      'https://www.linkedin.com/company/rebase',
    )
  })

  it('answers nothing for nothing', () => {
    expect(linkedinProfile('')).toBe('')
    expect(linkedinProfile('   ')).toBe('')
  })

  it.each([
    'https://twitter.com/ada',
    'linkedin.com.evil.com/in/ada',
    'evil.com/linkedin.com/in/ada',
    'javascript:alert(1)//linkedin.com/',
    'ada lovelace',
    'https://www.linkedin.com/in/ada\nBcc: qualcuno@altrove.it',
  ])('refuses %j', (input) => {
    expect(linkedinProfile(input)).toBeNull()
  })
})

describe('linkedinFieldValue', () => {
  it('reduces a profile that arrives in one go to the name the field asks for', () => {
    expect(linkedinFieldValue('https://it.linkedin.com/in/ada-lovelace/?trk=share')).toBe('ada-lovelace')
    expect(linkedinFieldValue(ADA)).toBe('ada-lovelace')
  })

  it('leaves typing alone, so an address typed by hand stays an address', () => {
    let field = ''
    for (const key of 'linkedin.com/in/ada-lovelace/?utm_source=share') {
      field = linkedinFieldValue(field + key, field)
    }
    expect(field).toBe('linkedin.com/in/ada-lovelace/?utm_source=share')
    expect(linkedinProfile(field)).toBe(ADA)
  })

  it('keeps another page as it is', () => {
    expect(linkedinFieldValue('https://www.linkedin.com/company/rebase')).toBe(
      'https://www.linkedin.com/company/rebase',
    )
  })

  it('shows the prefix only in front of a name', () => {
    expect(isLinkedinName('')).toBe(true)
    expect(isLinkedinName('ada-lovelace')).toBe(true)
    expect(isLinkedinName('https://www.linkedin.com/company/rebase')).toBe(false)
  })
})
