import Box from '@mui/material/Box';
import { useKeycloak } from '@react-keycloak/web';
import React from 'react';
const BottomBanner = (props) => {
  const { eligible, text = '', type = '', householdApplicationId = '' } = props;
  const { keycloak } = useKeycloak();
  if (householdApplicationId) {
    const origCreateLoginUrl = keycloak.createLoginUrl;
    keycloak.createLoginUrl = (options) => {
      let url = origCreateLoginUrl(options);
      url = url + '&nonce=' + encodeURIComponent(householdApplicationId);
      return url;
    };
  }
  const redirectUri = householdApplicationId
    ? `${window.location.origin}/householdForm`
    : `${window.location.origin}/form`;
  const buttonText =
    'Please answer the questions above to confirm you are eligible to apply for a rebate.';
  return (
    <>
      <div
        className={
          type === 'individual'
            ? 'start-application-individual'
            : 'start-application-spouse'
        }
      >
        <h1 id="start-text">{text}</h1>
        <Box id="bceid-login-square">
          <h1 id="BceidLoginTitle">BCeID</h1>
          <button
            type="button"
            className="button"
            disabled={!eligible}
            title={!eligible && buttonText}
            onClick={() =>
              keycloak.login({
                idpHint: 'bceid-basic',
                redirectUri: redirectUri
              })
            }
          >
            Login with BCeID
          </button>
          <div>
            <a
              href="https://www.bceid.ca/register/basic/account_details.aspx?type=regular&eServiceType=basic"
              target="_blank"
              rel="noopener noreferrer"
            >
              Get a Basic BCeID account
            </a>
          </div>
        </Box>
      </div>
    </>
  );
};

export default BottomBanner;
