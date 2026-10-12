/**
 * Fixed answers for local development and tests (PROVIDER=mock). Never use in production: it knows
 * a handful of made-up plates and returns extra fields on purpose, to prove the handler strips them.
 */

const KNOWN = {
  TST1001: { year: 2019, make: 'HONDA', model: 'CIVIC LX', vin: '1HGBH41JXMN109186', owner: 'Not A Real Person' },
  NEW1234: { year: '2021', make: 'Kia', model: 'Soul', vin: '5XYJ3E1B0MN000001' },
  UNK0001: { year: 2018, make: 'Toyota', model: 'Camry' },
  BADYEAR: { year: 1066, make: 'Ford', model: 'Model T' }
};

export async function lookup({ plate }) {
  return KNOWN[plate] || null;
}
