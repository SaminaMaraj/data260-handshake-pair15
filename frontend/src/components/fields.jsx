export function Fields({ fields, form, setForm }) {
  return <div className="form-grid">{fields.map(([name, label, type, required, maxLength]) => {
    const props = {
      id: name, name, required: Boolean(required), maxLength,
      value: form[name] ?? "",
      onChange: (event) => setForm({ ...form, [name]: event.target.value }),
    };
    return <div key={name} className={type === "textarea" || type === "json" ? "wide-field" : ""}>
      <label htmlFor={name}>{label}{required ? " *" : ""}</label>
      {type === "textarea" || type === "json" ? <textarea {...props} rows={3} />
        : type === "category" ? <select {...props}>
          <option value="">Choose a category</option>
          <option value="full_time">Full time</option><option value="part_time">Part time</option>
          <option value="on_campus">On campus</option><option value="internship">Internship</option>
        </select>
        : type === "checkbox" ? <input id={name} type="checkbox" checked={Boolean(form[name])}
          onChange={(event) => setForm({ ...form, [name]: event.target.checked })} />
        : <input {...props} type={["year", "cgpa", "salary"].includes(type) ? "number" : type}
          min={type === "year" ? 1901 : ["cgpa", "salary"].includes(type) ? 0 : undefined}
          max={type === "year" ? 2155 : type === "cgpa" ? 99.99 : type === "salary" ? 9999999999.99 : undefined}
          step={type === "year" ? 1 : ["cgpa", "salary"].includes(type) ? "0.01" : undefined} />}
    </div>;
  })}</div>;
}
