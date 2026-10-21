using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using TMPro;
using UnityEngine.UIElements;
using UnityEngine.XR;
using System.Linq;
using System.Runtime.ExceptionServices;
using UnityEngine.Rendering;

public class Textinput : MonoBehaviour
{
    public GameObject cursorPrefab;
    public GameObject cursor;
    public float blinkInterval = 0.5f;
    public RectTransform cursorRect;
    public TextMeshProUGUI InputTextFrame;
    public string DisplayString;
    public GetText GT;

    private List<int> Pos_li;

    private string originalText;
    private int cursorPosition;
    private float blinkTimer;
    // Start is called before the first frame update
    void Start()
    {
        Pos_li = new List<int>(10);
        InputTextFrame = GetComponent<TextMeshProUGUI>();
        originalText = InputTextFrame.text;

        // Create the cursor object
        cursor = Instantiate(cursorPrefab, transform);
        cursor.transform.SetParent(transform);
        cursorRect = cursor.GetComponent<RectTransform>();

        // Set the cursor position to the end of the text
        cursorPosition = InputTextFrame.text.Length;

        // Start the blink timer
        blinkTimer = blinkInterval;
    }

    // Update is called once per frame
    void Update()
    {
        // Update the cursor position if the text has changed
        if (InputTextFrame.text != originalText)
        {
            originalText = InputTextFrame.text;
            cursorPosition = InputTextFrame.text.Length;
        }

        // Get the position of the character at the cursor position
        Vector3 cursorPos = Vector3.zero;
        if (cursorPosition > 0)
        {
            TMP_CharacterInfo charInfo = InputTextFrame.textInfo.characterInfo[cursorPosition -1];
            cursorPos = new Vector3(charInfo.bottomRight.x+5f, charInfo.topLeft.y-3f, 0f);
        }

        // Set the position of the cursor
        cursorRect.anchoredPosition = cursorPos;

        // Blink the cursor
        blinkTimer -= Time.deltaTime;
        if (blinkTimer <= 0f)
        {
            cursor.SetActive(!cursor.activeSelf);
            blinkTimer = blinkInterval;
        }

        // Handle input
        //if (Input.GetKeyDown(KeyCode.LeftArrow))
        //{
        //    if (cursorPosition > 0)
        //    {
        //        cursorPosition--;
        //    }
        //}
        //else if (Input.GetKeyDown(KeyCode.RightArrow))
        //{
        //    if (cursorPosition < InputTextFrame.text.Length)
        //    {
        //        cursorPosition++;
        //    }
        //}
        //else if (Input.GetKeyDown(KeyCode.Backspace))
        //{
        //    if (cursorPosition > 0)
        //    {
        //        InputTextFrame.text = InputTextFrame.text.Remove(cursorPosition - 1, 1);
        //        cursorPosition--;
        //    }
        //}
        //else if (Input.GetKeyDown(KeyCode.Delete))
        //{
        //    if (cursorPosition < InputTextFrame.text.Length)
        //    {
        //        InputTextFrame.text = InputTextFrame.text.Remove(cursorPosition, 1);
        //    }
        //}
        //else if (Input.inputString.Length > 0)
        //{
        //    InputTextFrame.text = InputTextFrame.text.Insert(cursorPosition, Input.inputString);
        //    cursorPosition += Input.inputString.Length;
        //}
    }
}
