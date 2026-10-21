//using System.Collections;
//using System.Collections.Generic;
//using UnityEngine;
//using TMPro;
//using UnityEngine.Experimental.AI;
//using Oculus.Platform.Samples.VrBoardGame;

//public class ShiftKey : MonoBehaviour
//{
//    public Transform parentObject;
//    public Material ShiftKeyHighlightedMaterial, OriginalStateMaterial; 

//    GameObject ShiftKeyMesh;
//    List<TextMeshPro> KeyTexts = new List<TextMeshPro>();
//    private TextMeshPro KeyText;
//    MeshRenderer ShiftKeyMeshRenderer;

//    // Start is called before the first frame update
//    void Start()
//    {
//        ShiftKeyMesh.GetComponent<MeshRenderer>();
//        ShiftKeyMesh = gameObject;
//        foreach (Transform child in parentObject)
//        {
//            KeyText = child.GetComponentInChildren<TextMeshPro>();
//            KeyTexts.Add(KeyText);
//        }
//    }


//    /// <summary>
//    /// Highlight shift key when shift key is pressed. 
//    /// </summary>
//    void HighlightShiftKey()
//    {
//        ShiftKeyMeshRenderer.material = ShiftKeyHighlightedMaterial;
//    }

//    /// <summary>
//    /// Set all the text to Uppercase when shift key is pressed.
//    /// </summary>
//    void SetUpperCase()
//    {
//        foreach (TextMeshPro KeyText in KeyTexts)
//        {
//            KeyText.text = KeyText.text.ToUpper();
//        }
//    }

//    /// <summary>
//    /// Set Shift key to its original state
//    /// </summary>
//    void ReturnOriginalState()
//    {
//        ShiftKeyMeshRenderer.material = OriginalStateMaterial;
//    }

//    // Update is called once per frame
//    void Update()
//    {
//    }
//}
