import useApiData from './useApiData';
import { Photo } from './PartACommon';
export default function CompanyDetails({companyId,user,onUnauthorized}){
  const company=useApiData(`/companies/${companyId}`,user,onUnauthorized);
  const contact=useApiData(`/profiles/${companyId}/contact`,user,onUnauthorized);
  if(company.loading)return <p role="status">Loading company...</p>;
  if(company.error)return <p role="alert">{company.error}</p>;
  return <section className="card p-3 my-3"><h2>{company.data.company_name}</h2><Photo url={company.data.profile_picture_url} user={user}/>
    <p>{company.data.description}</p><p>{company.data.location}</p>
    <p>Contact: {contact.data?.email || contact.error || 'Loading...'} · {company.data.contact_phone || 'No phone provided'}</p>
  </section>;
}
