// Zonas de medición del cuerpo. x negativo = lado DERECHO de la persona (mira a cámara).
export const ZONES = [
  { id: "neck", label: "Cuello", fields: [["neck", "Perímetro de cuello"]], pos: [0, 1.535, 0], r: 0.068, flat: 0.9,
    tip: "Debajo de la nuez, cinta horizontal." },
  { id: "shoulders", label: "Hombros", fields: [["shoulders", "Perímetro de hombros"]], pos: [0, 1.425, 0], r: 0.25, flat: 0.5,
    tip: "Por la parte más ancha de los deltoides." },
  { id: "chest", label: "Pecho", fields: [["chest", "Perímetro de pecho"]], pos: [0, 1.31, 0.005], r: 0.185, flat: 0.68,
    tip: "A la altura de los pezones, al final de una exhalación normal." },
  { id: "waist", label: "Cintura", fields: [["waist", "Cintura (parte más angosta)"]], pos: [0, 1.11, 0], r: 0.16, flat: 0.68,
    tip: "En la parte más angosta del torso, sin apretar." },
  { id: "abdomen", label: "Abdomen", fields: [["abdomen", "Abdomen (a la altura del ombligo)"]], pos: [0, 1.0, 0.004], r: 0.168, flat: 0.68,
    tip: "Horizontal a la altura del ombligo, relajado." },
  { id: "hip", label: "Cadera", fields: [["hip", "Cadera (glúteos)"]], pos: [0, 0.885, 0], r: 0.182, flat: 0.72,
    tip: "Por la parte más prominente de los glúteos." },
  { id: "arm_right", label: "Brazo derecho", fields: [["arm_right", "Relajado"], ["arm_flexed_right", "Contraído"]], pos: [-0.232, 1.27, 0], r: 0.066, tilt: 0.12 },
  { id: "arm_left", label: "Brazo izquierdo", fields: [["arm_left", "Relajado"], ["arm_flexed_left", "Contraído"]], pos: [0.232, 1.27, 0], r: 0.066, tilt: -0.12 },
  { id: "forearm_right", label: "Antebrazo derecho", fields: [["forearm_right", "Perímetro máximo"]], pos: [-0.257, 1.03, 0], r: 0.056, tilt: 0.06 },
  { id: "forearm_left", label: "Antebrazo izquierdo", fields: [["forearm_left", "Perímetro máximo"]], pos: [0.257, 1.03, 0], r: 0.056, tilt: -0.06 },
  { id: "wrist", label: "Muñeca", fields: [["wrist", "Muñeca (der.)"]], pos: [-0.266, 0.905, 0], r: 0.043 },
  { id: "thigh_right", label: "Muslo derecho", fields: [["thigh_right", "Perímetro de muslo"]], pos: [-0.092, 0.71, 0], r: 0.094, tilt: 0.04 },
  { id: "thigh_left", label: "Muslo izquierdo", fields: [["thigh_left", "Perímetro de muslo"]], pos: [0.092, 0.71, 0], r: 0.094, tilt: -0.04 },
  { id: "calf_right", label: "Pantorrilla derecha", fields: [["calf_right", "Perímetro máximo"]], pos: [-0.086, 0.36, 0], r: 0.07 },
  { id: "calf_left", label: "Pantorrilla izquierda", fields: [["calf_left", "Perímetro máximo"]], pos: [0.086, 0.36, 0], r: 0.07 },
];

export const SKINFOLD_FIELDS = [
  ["sf_chest", "Pectoral"], ["sf_midaxillary", "Axilar medio"], ["sf_triceps", "Tríceps"],
  ["sf_subscapular", "Subescapular"], ["sf_abdominal", "Abdominal"], ["sf_suprailiac", "Suprailíaco"], ["sf_thigh", "Muslo"],
];

export const zoneFilled = (z, values) => z.fields.some(([f]) => values[f] !== "" && values[f] != null);
